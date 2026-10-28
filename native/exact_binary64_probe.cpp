#include "exact_binary64.hpp"

#include <cctype>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <limits>
#include <string>
#include <string_view>

namespace {

using openpoker::exact_binary64::ConversionError;
using openpoker::exact_binary64::Integer;

constexpr std::size_t kMaximumLineBytes = 1U << 20;
constexpr std::size_t kMaximumHexDigits = openpoker::exact_binary64::kMaximumInputBits / 4;
constexpr std::string_view kProtocol = "OPENPOKER_EXACT_BINARY64_V1";

enum class LineStatus { line, end, too_long };

LineStatus read_bounded_line(std::istream& input, std::string& line) {
    line.clear();
    bool saw_any = false;
    for (;;) {
        const int ch = input.get();
        if (ch == std::char_traits<char>::eof()) {
            if (!saw_any) return LineStatus::end;
            break;
        }
        saw_any = true;
        if (ch == '\n') break;
        if (line.size() == kMaximumLineBytes) {
            return LineStatus::too_long;
        }
        line.push_back(static_cast<char>(ch));
    }
    if (!line.empty() && line.back() == '\r') line.pop_back();
    return LineStatus::line;
}

int hex_value(char ch) {
    if (ch >= '0' && ch <= '9') return ch - '0';
    if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
    if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
    return -1;
}

std::size_t hex_bit_length(std::string_view token) {
    std::size_t first = 0;
    while (first < token.size() && token[first] == '0') ++first;
    if (first == token.size()) return 0;
    const int top = hex_value(token[first]);
    if (top < 0) return std::numeric_limits<std::size_t>::max();
    std::size_t top_bits = 0;
    for (int value = top; value != 0; value >>= 1) ++top_bits;
    const auto tail_digits = token.size() - first - 1;
    if (tail_digits > (std::numeric_limits<std::size_t>::max() - top_bits) / 4) {
        return std::numeric_limits<std::size_t>::max();
    }
    return tail_digits * 4 + top_bits;
}

Integer parse_hex_bounded(std::string_view token, bool allow_negative) {
    bool negative = false;
    if (allow_negative && !token.empty() && token.front() == '-') {
        negative = true;
        token.remove_prefix(1);
    } else if (!token.empty() && (token.front() == '+' || token.front() == '-')) {
        throw std::invalid_argument("sign not allowed");
    }
    if (token.empty()) throw std::invalid_argument("empty hex token");
    if (token.size() > kMaximumHexDigits) throw std::length_error("hex token cap");
    for (char ch : token) {
        if (hex_value(ch) < 0) throw std::invalid_argument("invalid hex digit");
    }
    const auto bits = hex_bit_length(token);
    if (bits > openpoker::exact_binary64::kMaximumInputBits) {
        throw std::length_error("input bit cap");
    }

    Integer value = 0;
    for (char ch : token) {
        value <<= 4;
        value += hex_value(ch);
    }
    return negative && value != 0 ? -value : value;
}

std::string_view trim(std::string_view value) {
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.front()))) {
        value.remove_prefix(1);
    }
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back()))) {
        value.remove_suffix(1);
    }
    return value;
}

bool split_record(std::string_view line, std::string_view& numerator,
                  std::string_view& denominator) {
    line = trim(line);
    const auto split = line.find_first_of(" \t\r\n\f\v");
    if (split == std::string_view::npos) return false;
    numerator = line.substr(0, split);
    line.remove_prefix(split);
    line = trim(line);
    const auto second_split = line.find_first_of(" \t\r\n\f\v");
    if (second_split == std::string_view::npos) {
        denominator = line;
        return !numerator.empty() && !denominator.empty();
    }
    denominator = line.substr(0, second_split);
    return denominator.size() > 0 && trim(line.substr(second_split)).empty();
}

void write_error(const char* code) {
    std::cout << "ERR\t" << code << '\n';
}

void process_line(std::string_view line) {
    std::string_view numerator_token;
    std::string_view denominator_token;
    if (!split_record(line, numerator_token, denominator_token)) {
        write_error("invalid_record");
        return;
    }
    try {
        Integer numerator = parse_hex_bounded(numerator_token, true);
        Integer denominator = parse_hex_bounded(denominator_token, false);
        const auto result = openpoker::exact_binary64::convert(numerator, denominator);
        std::cout << "OK\t" << std::hex << std::setw(16) << std::setfill('0')
                  << result.bits << std::dec << '\t'
                  << result.receipt.peak_input_bits << '\t'
                  << result.receipt.peak_scratch_bits << '\t'
                  << result.receipt.modeled_work << '\n';
    } catch (const ConversionError& error) {
        write_error(openpoker::exact_binary64::error_name(error.code()));
    } catch (const std::length_error&) {
        write_error("input_bit_limit");
    } catch (const std::exception&) {
        write_error("invalid_record");
    }
}

}  // namespace

int main() {
    std::string line;
    if (read_bounded_line(std::cin, line) != LineStatus::line || line != kProtocol) {
        write_error("protocol_version");
        return 2;
    }
    std::cout << "READY\t" << kProtocol << '\n';
    for (;;) {
        const auto status = read_bounded_line(std::cin, line);
        if (status == LineStatus::end) return 0;
        if (status == LineStatus::too_long) {
            write_error("line_too_long");
            return 3;
        }
        process_line(line);
    }
}
