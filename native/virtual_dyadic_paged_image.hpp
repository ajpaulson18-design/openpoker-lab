#pragma once

// Bounded little-endian on-disk image with a committed-only direct-mapped cache.
#include <algorithm>
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <limits>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

namespace openpoker::virtual_dyadic_paged_image {

inline constexpr std::size_t n9_image_words = 606730;
inline constexpr std::size_t n10_image_words = 2962722;
inline constexpr std::size_t default_page_words = 4096;
inline constexpr std::size_t default_cache_pages = 16;
inline constexpr std::size_t maximum_resident_bytes = 1024 * 1024;
inline constexpr std::uint64_t maximum_read_words = 16777216;
inline constexpr std::uint64_t maximum_write_words = 3ULL * n9_image_words;
inline constexpr std::uint64_t maximum_logical_requests = 1000000;
inline constexpr std::uint64_t n10_read_words = 11000000;
inline constexpr std::uint64_t n10_write_words = 3ULL * n10_image_words;
inline constexpr std::uint64_t n10_logical_requests = 3091726;
enum class Profile { legacy, proof10 };

struct Limits {
    std::size_t image_words = n9_image_words;
    std::size_t page_words = default_page_words;
    std::size_t cache_pages = default_cache_pages;
    std::uint64_t read_words = maximum_read_words;
    std::uint64_t write_words = maximum_write_words;
    std::uint64_t requests = maximum_logical_requests;
    std::size_t cache_banks = 1; // appended; cache_pages is the total across banks
    Profile profile = Profile::legacy;
};

struct Receipt {
    std::uint64_t read_words = 0;             // physical words fetched from disk
    std::uint64_t logical_read_words = 0;     // words returned, including cache hits
    std::uint64_t write_words = 0;            // physical initialization plus staged writes
    std::uint64_t read_calls = 0;
    std::uint64_t stage_calls = 0;
    std::uint64_t physical_read_requests = 0; // page-load operations
    std::uint64_t physical_write_requests = 0;// initialization/staging chunks
    std::uint64_t cache_hits = 0;
    std::uint64_t cache_misses = 0;           // includes page loads
    std::uint64_t completed_sweeps = 0;
};

class Image {
public:
    // This forecast performs checked arithmetic and validation only; it allocates nothing.
    [[nodiscard]] static std::size_t resident_bytes(const Limits& limits) {
        validate(limits);
        const auto cached_words = checked_mul(limits.page_words, limits.cache_pages);
        const auto word_bytes = checked_mul(cached_words, sizeof(std::uint64_t));
        const auto bitmap_bytes = limits.image_words / 8 + (limits.image_words % 8 != 0);
        const auto tag_bytes = checked_mul(limits.cache_pages, sizeof(std::size_t));
        const auto total = checked_add(checked_add(checked_add(word_bytes, limits.cache_pages), tag_bytes), bitmap_bytes);
        if (total > maximum_resident_bytes) throw std::invalid_argument("resident image budget exceeded");
        return total;
    }

    Image(const std::filesystem::path& fresh_directory, Limits limits)
        : limits_(limits), resident_bytes_(resident_bytes(limits)), cache_(limits.cache_pages * limits.page_words),
          cache_valid_(limits.cache_pages, 0), cache_tags_(limits.cache_pages, 0),
          staged_bits_(limits.image_words / 8 + (limits.image_words % 8 != 0), 0) {
        std::error_code ec;
        if (!std::filesystem::create_directory(fresh_directory, ec) || ec)
            throw std::runtime_error("fresh image directory could not be created exclusively");
        files_[0].open(fresh_directory / "committed.bin", std::ios::binary | std::ios::in | std::ios::out | std::ios::trunc);
        files_[1].open(fresh_directory / "staged.bin", std::ios::binary | std::ios::in | std::ios::out | std::ios::trunc);
        if (!files_[0] || !files_[1]) throw std::runtime_error("cannot create private image files");
        for (std::size_t at=0; at<limits_.image_words;) {
            const auto n=std::min(limits_.image_words-at,limits_.page_words);
            write_words(files_[0],at,{cache_.data(),n});
            at+=n;
            receipt_.write_words+=n;
            ++receipt_.physical_write_requests;
        }
        files_[0].flush();
        if (!files_[0]) throw std::runtime_error("cannot initialize committed image");
    }

    Image(const Image&) = delete;
    Image& operator=(const Image&) = delete;
    Image(Image&&) = delete;
    Image& operator=(Image&&) = delete;

    void begin_sweep() {
        if (sweep_open_) throw std::logic_error("sweep already open");
        std::fill(staged_bits_.begin(), staged_bits_.end(), static_cast<unsigned char>(0));
        staged_words_ = 0;
        sweep_open_ = true;
    }

    void read(std::size_t offset, std::span<std::uint64_t> output, std::size_t bank = 0) {
        if (bank >= limits_.cache_banks) throw std::out_of_range("cache bank outside bounds");
        check_range(offset, output.size());
        check_request_admission(1);
        if (output.empty()) { ++receipt_.read_calls; return; }
        const auto miss_words = predicted_read_words(offset, output.size(), bank);
        if (receipt_.read_words > limits_.read_words || miss_words > limits_.read_words - receipt_.read_words)
            throw std::length_error("physical read word limit exceeded");
        std::size_t done = 0;
        while (done < output.size()) {
            const std::size_t pos = offset + done;
            const std::size_t page = pos / limits_.page_words;
            const std::size_t bank_pages = limits_.cache_pages / limits_.cache_banks;
            const std::size_t slot = bank * bank_pages + page % bank_pages;
            const std::size_t in_page = pos % limits_.page_words;
            const std::size_t count = std::min(output.size() - done, limits_.page_words - in_page);
            if (cache_valid_[slot] && cache_tags_[slot] == page) {
                ++receipt_.cache_hits;
            } else {
                ++receipt_.cache_misses;
                load_page(page, slot);
            }
            std::copy_n(cache_.data() + slot * limits_.page_words + in_page, count, output.data() + done);
            done += count;
        }
        receipt_.logical_read_words += output.size();
        ++receipt_.read_calls;
    }

    void stage(std::size_t offset, std::span<const std::uint64_t> input) {
        if (!sweep_open_) throw std::logic_error("stage requires an open sweep");
        check_range(offset, input.size());
        check_request_admission(1);
        for (std::size_t i = 0; i < input.size(); ++i)
            if (bit_is_set(offset + i)) throw std::invalid_argument("overlapping staged range");
        if (input.size() > limits_.image_words - staged_words_)
            throw std::invalid_argument("staged image overflow");
        if (receipt_.write_words > limits_.write_words || input.size() > limits_.write_words - receipt_.write_words)
            throw std::length_error("write word limit exceeded");
        if (!input.empty()) {
            write_words(files_[1-committed_],offset,input);
            receipt_.write_words+=input.size();
            ++receipt_.physical_write_requests;
            for (std::size_t i = 0; i < input.size(); ++i) set_bit(offset + i);
            staged_words_ += input.size();
        }
        ++receipt_.stage_calls;
    }

    void commit_sweep() {
        if (!sweep_open_) throw std::logic_error("no open sweep");
        if (staged_words_ != limits_.image_words) throw std::logic_error("incomplete staged image");
        // The exact word count and overlap guard prove complete coverage.
        auto& staged=files_[1-committed_];
        staged.flush();
        if (!staged) throw std::runtime_error("cannot flush staged image");
        committed_=1-committed_;
        ++receipt_.completed_sweeps;
        sweep_open_ = false;
        std::fill(cache_valid_.begin(), cache_valid_.end(), static_cast<unsigned char>(0));
    }

    [[nodiscard]] const Receipt& receipt() const noexcept { return receipt_; }
    [[nodiscard]] std::size_t resident_reservation_bytes() const noexcept { return resident_bytes_; }

private:
    Limits limits_;
    std::size_t resident_bytes_;
    std::vector<std::uint64_t> cache_;
    std::vector<unsigned char> cache_valid_;
    std::vector<std::size_t> cache_tags_;
    std::vector<unsigned char> staged_bits_;
    std::size_t staged_words_ = 0;
    bool sweep_open_ = false;
    Receipt receipt_;
    std::array<std::fstream,2> files_;
    std::size_t committed_ = 0;

    static std::size_t checked_mul(std::size_t a, std::size_t b) {
        if (b && a > std::numeric_limits<std::size_t>::max() / b) throw std::overflow_error("size overflow");
        return a * b;
    }
    static std::size_t checked_add(std::size_t a, std::size_t b) {
        if (a > std::numeric_limits<std::size_t>::max() - b) throw std::overflow_error("size overflow");
        return a + b;
    }
    static void validate(const Limits& l) {
        const bool proof10=l.profile==Profile::proof10;
        if (proof10 && (l.image_words!=n10_image_words || l.page_words!=default_page_words ||
            l.cache_pages!=default_cache_pages || l.cache_banks!=2))
            throw std::invalid_argument("invalid ten-card image geometry");
        if (std::endian::native!=std::endian::little || !l.image_words || !l.page_words || !l.cache_pages ||
            !l.cache_banks || l.cache_banks > 2 ||
            l.cache_pages % l.cache_banks != 0 ||
            (l.profile!=Profile::legacy && !proof10) ||
            (!proof10 && l.image_words > n9_image_words) || l.page_words > 8192 || l.cache_pages > 16 ||
            l.read_words > (proof10?n10_read_words:maximum_read_words) ||
            l.write_words > (proof10?n10_write_words:maximum_write_words) ||
            l.write_words < l.image_words || l.requests > (proof10?n10_logical_requests:maximum_logical_requests))
            throw std::invalid_argument("invalid image limits");
        if (l.image_words > static_cast<std::size_t>(std::numeric_limits<std::streamoff>::max()) / 8)
            throw std::overflow_error("image byte size exceeds stream range");
    }
    void check_range(std::size_t offset, std::size_t count) const {
        if (offset > limits_.image_words || count > limits_.image_words - offset || count>limits_.page_words)
            throw std::out_of_range("image range outside bounds");
    }
    void check_request_admission(std::uint64_t n) const {
        if (receipt_.read_calls + receipt_.stage_calls > limits_.requests ||
            n > limits_.requests - (receipt_.read_calls + receipt_.stage_calls))
            throw std::length_error("logical request limit exceeded");
    }
    static void write_words(std::fstream& f, std::size_t word_offset,std::span<const std::uint64_t> input) {
        const auto bytes=input.size_bytes();
        if (word_offset > static_cast<std::size_t>(std::numeric_limits<std::streamoff>::max()) / 8 ||
            bytes > static_cast<std::size_t>(std::numeric_limits<std::streamsize>::max()))
            throw std::overflow_error("stream offset overflow");
        f.clear();
        f.seekp(static_cast<std::streamoff>(word_offset * 8));
        f.write(reinterpret_cast<const char*>(input.data()),static_cast<std::streamsize>(bytes));
        if (!f) throw std::runtime_error("image write failed");
    }
    void load_page(std::size_t page, std::size_t slot) {
        const auto first = page * limits_.page_words;
        const auto n = std::min(limits_.page_words, limits_.image_words - first);
        auto& committed=files_[committed_];
        cache_valid_[slot]=false;
        committed.clear();
        committed.seekg(static_cast<std::streamoff>(first * 8));
        committed.read(reinterpret_cast<char*>(cache_.data()+slot*limits_.page_words),static_cast<std::streamsize>(n*8));
        if (!committed || committed.gcount()!=static_cast<std::streamsize>(n*8)) throw std::runtime_error("short image read");
        cache_tags_[slot] = page;
        cache_valid_[slot] = true;
        ++receipt_.physical_read_requests;
        receipt_.read_words += n;
    }
    std::uint64_t predicted_read_words(std::size_t offset, std::size_t count, std::size_t bank) const {
        // Simulate direct-map tags without allocating; page count is bounded by the admitted request.
        std::uint64_t words = 0;
        std::size_t done = 0;
        std::size_t previous_slot=limits_.cache_pages;
        while (done < count) {
            const auto pos = offset + done;
            const auto page = pos / limits_.page_words;
            const auto bank_pages = limits_.cache_pages / limits_.cache_banks;
            const auto slot = bank * bank_pages + page % bank_pages;
            if (slot==previous_slot || !(cache_valid_[slot] && cache_tags_[slot] == page))
                words += std::min(limits_.page_words, limits_.image_words - page * limits_.page_words);
            previous_slot=slot;
            done += std::min(count - done, limits_.page_words - (pos % limits_.page_words));
        }
        return words;
    }
    bool bit_is_set(std::size_t i) const noexcept { return (staged_bits_[i / 8] & (1u << (i % 8))) != 0; }
    void set_bit(std::size_t i) noexcept { staged_bits_[i / 8] |= static_cast<unsigned char>(1u << (i % 8)); }
};

} // namespace openpoker::virtual_dyadic_paged_image
