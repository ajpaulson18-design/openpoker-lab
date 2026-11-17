// Windows x64 periodic wall-time stack observer for one explicitly owned child.
// This wrapper does not instrument, relink, or alter the child.
#if defined(_WIN32) && defined(_WIN64) && (defined(_M_X64) || defined(__x86_64__))
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <DbgHelp.h>
#include <Psapi.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#pragma comment(lib,"Dbghelp.lib")
#pragma comment(lib,"Psapi.lib")

namespace owned_child_stack_sample {
constexpr std::size_t max_samples=1024,max_frames=64,max_modules=64;
constexpr std::size_t max_target_read=64*1024,max_callback_read=64*1024;
constexpr std::size_t max_image_bytes=64*1024*1024,max_total_image_bytes=256*1024*1024,max_callback_calls=4096;
constexpr std::size_t max_report_bytes=4*1024*1024,max_path_chars=32768;
constexpr std::uint32_t default_interval_ms=20,max_interval_ms=1000;
constexpr std::chrono::seconds child_deadline{60};
constexpr std::chrono::milliseconds pause_deadline{250};
constexpr DWORD terminal_exit_observation_ms=250;

struct Failure final:std::runtime_error { using std::runtime_error::runtime_error; };
struct Options {
    std::wstring child,scratch,report,symbols;
    std::uint32_t interval_ms=default_interval_ms;
    bool disabled=false;
};

std::wstring utf8_to_wide(std::string_view text) {
    if (text.empty()) return {};
    const int count=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),nullptr,0);
    if (count<=0) throw Failure("invalid UTF-8 argument");
    std::wstring result(static_cast<std::size_t>(count),L'\0');
    if (MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),result.data(),count)!=count)
        throw Failure("UTF-8 argument conversion failed");
    return result;
}

Options parse_options(int argc,wchar_t** argv) {
    Options result;
    bool have_child=false,have_scratch=false,have_report=false,have_symbols=false,have_interval=false;
    for (int i=1;i<argc;++i) {
        const std::wstring_view option(argv[i]);
        if (option==L"--disabled") {
            if (result.disabled) throw Failure("duplicate --disabled");
            result.disabled=true;
        } else if (option==L"--child" || option==L"--scratch" || option==L"--report" ||
                   option==L"--symbols" || option==L"--interval-ms") {
            if (++i>=argc) throw Failure("option requires a value");
            const std::wstring value(argv[i]);
            if (option==L"--child") {if (have_child) throw Failure("duplicate --child");result.child=value;have_child=true;}
            else if (option==L"--scratch") {if (have_scratch) throw Failure("duplicate --scratch");result.scratch=value;have_scratch=true;}
            else if (option==L"--report") {if (have_report) throw Failure("duplicate --report");result.report=value;have_report=true;}
            else if (option==L"--symbols") {if (have_symbols) throw Failure("duplicate --symbols");result.symbols=value;have_symbols=true;}
            else {
                if (have_interval || value.empty()) throw Failure("invalid or duplicate --interval-ms");
                std::uint64_t parsed=0;
                for (const wchar_t c:value) {
                    if (c<L'0' || c>L'9' || parsed>(std::numeric_limits<std::uint32_t>::max()-(c-L'0'))/10)
                        throw Failure("invalid --interval-ms");
                    parsed=parsed*10+static_cast<unsigned>(c-L'0');
                }
                if (!parsed || parsed>max_interval_ms) throw Failure("--interval-ms is outside 1..1000");
                result.interval_ms=static_cast<std::uint32_t>(parsed);have_interval=true;
            }
        } else throw Failure("unknown sampler option");
    }
    if (!have_child || !have_scratch || !have_report || !have_symbols)
        throw Failure("required options: --child EXE --scratch ABS --report ABS --symbols ABS");
    return result;
}

bool absolute_path(const std::wstring& value) {
    return !value.empty() && std::filesystem::path(value).is_absolute();
}

void validate_options(const Options& options) {
    for (const auto* value:{&options.child,&options.scratch,&options.report,&options.symbols})
        if (value->size()>=max_path_chars) throw Failure("sampler path capacity exceeded");
    if (!absolute_path(options.child) || !absolute_path(options.scratch) ||
        !absolute_path(options.report) || !absolute_path(options.symbols))
        throw Failure("child, scratch, report, and symbols paths must be absolute");
    std::error_code error;
    if (!std::filesystem::is_regular_file(options.child,error) || error)
        throw Failure("child executable is not a readable regular file");
    error.clear();
    if (std::filesystem::exists(options.scratch,error) && !std::filesystem::is_directory(options.scratch,error))
        throw Failure("scratch path must be a new or existing directory");
    if (error) throw Failure("scratch path status failed");
    error.clear();
    if (!std::filesystem::is_directory(options.symbols,error) || error)
        throw Failure("symbols path must be an existing empty directory");
    if (std::filesystem::directory_iterator(options.symbols,error)!=std::filesystem::directory_iterator{} || error)
        throw Failure("symbols directory must be empty; symbol downloads are disabled");
    error.clear();
    if (std::filesystem::exists(options.report,error) || error)
        throw Failure("report path must be new and must not already exist");
    const auto parent=std::filesystem::path(options.report).parent_path();
    if (parent.empty() || !std::filesystem::is_directory(parent,error) || error)
        throw Failure("report parent must be an existing directory");
}

std::string wide_to_utf8(std::wstring_view text) {
    if (text.empty()) return {};
    if (text.size()>static_cast<std::size_t>(std::numeric_limits<int>::max())) throw Failure("path is too long");
    const int count=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),nullptr,0,nullptr,nullptr);
    if (count<=0) throw Failure("UTF-8 path conversion failed");
    std::string result(static_cast<std::size_t>(count),'\0');
    if (WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),result.data(),count,nullptr,nullptr)!=count)
        throw Failure("UTF-8 path conversion failed");
    return result;
}

class Json final {
    std::string data_;
public:
    void raw(std::string_view value) {
        if (value.size()>max_report_bytes-data_.size()) throw Failure("report exceeds 4 MiB cap");
        data_.append(value);
    }
    void quoted(std::string_view value) {
        raw("\"");
        constexpr char hex[]="0123456789abcdef";
        for (const unsigned char c:value) {
            if (c=='"' || c=='\\') {const char pair[2]={'\\',static_cast<char>(c)};raw({pair,2});}
            else if (c<0x20) {char escaped[6]={'\\','u','0','0',hex[c>>4],hex[c&15]};raw({escaped,6});}
            else {const char byte=static_cast<char>(c);raw({&byte,1});}
        }
        raw("\"");
    }
    [[nodiscard]] const std::string& str() const noexcept { return data_; }
};

std::string hex64(std::uint64_t value) {
    std::ostringstream text;text<<"0x"<<std::hex<<value;return text.str();
}

struct Handle final {
    HANDLE value=nullptr;
    Handle()=default;explicit Handle(HANDLE h):value(h) {}
    Handle(const Handle&)=delete;Handle& operator=(const Handle&)=delete;
    Handle(Handle&& other) noexcept:value(other.value){other.value=nullptr;}
    Handle& operator=(Handle&& other) noexcept {if(this!=&other){reset();value=other.value;other.value=nullptr;}return *this;}
    ~Handle(){reset();}
    void reset(HANDLE next=nullptr) noexcept {if(value && value!=INVALID_HANDLE_VALUE) CloseHandle(value);value=next;}
    [[nodiscard]] HANDLE get() const noexcept{return value;}
    [[nodiscard]] explicit operator bool() const noexcept{return value && value!=INVALID_HANDLE_VALUE;}
};

std::wstring quote_argument(std::wstring_view value) {
    std::wstring result=L"\"";
    std::size_t slashes=0;
    for (const wchar_t c:value) {
        if (c==L'\\') {++slashes;continue;}
        if (c==L'"') {result.append(slashes*2+1,L'\\');result.push_back(c);slashes=0;continue;}
        result.append(slashes,L'\\');slashes=0;result.push_back(c);
    }
    result.append(slashes*2,L'\\');result.push_back(L'"');
    return result;
}

struct Range { std::uint32_t begin=0,end=0; };
struct Module {
    HMODULE handle=nullptr;
    std::uint64_t base=0;
    std::uint32_t size=0;
    std::wstring path;
    Handle file,mapping;
    void* image=nullptr;
    bool image_valid=false;
    std::uint64_t file_bytes=0;
    std::vector<Range> blocked;
    std::array<Range,96> readonly_ranges{};
    std::size_t readonly_count=0;
    DWORD exception_rva=0,exception_size=0;
    std::string identity_error;
    ~Module(){if(image)UnmapViewOfFile(image);}
    Module()=default;
    Module(const Module&)=delete;
    Module& operator=(const Module&)=delete;
    Module(Module&& other) noexcept
        :handle(other.handle),base(other.base),size(other.size),path(std::move(other.path)),
         file(std::move(other.file)),mapping(std::move(other.mapping)),image(other.image),
         image_valid(other.image_valid),file_bytes(other.file_bytes),blocked(std::move(other.blocked)),
         readonly_ranges(other.readonly_ranges),readonly_count(other.readonly_count),
         exception_rva(other.exception_rva),exception_size(other.exception_size),identity_error(std::move(other.identity_error)) {
        other.image=nullptr;
    }
    Module& operator=(Module&&)=delete;
};

struct CaptureApi {
    bool suspend_called=false,context_called=false,context_succeeded=false,resume_called=false;
    DWORD suspend_return=DWORD(-1),suspend_error=0,context_error=0,resume_return=DWORD(-1),resume_error=0;
};
struct Snapshot {
    CaptureApi api;
    bool non_api_error=false;
    DWORD64 rip=0,rsp=0,rbp=0;
    CONTEXT context{};
    std::array<unsigned char,max_target_read> stack{};
    std::size_t stack_bytes=0,target_read_bytes=0;
    bool stack_truncated=false;
    const char* capture_error="";
    std::uint64_t pause_ns=0;
};
struct Frame {DWORD64 pc=0,sp=0;};
struct WalkResult {
    std::array<Frame,max_frames> frames{};
    std::size_t count=0,callback_calls=0,callback_bytes=0,stack_callback_bytes=0,module_callback_bytes=0;
    std::size_t callback_failures=0,budget_denials=0,unmapped_reads=0,metadata_calls=0;
    bool seed_echo_skipped=false;
    std::string stop_reason="not_attempted";
};
struct SampleRecord {
    CaptureApi api;
    std::uint64_t elapsed_ms=0,pause_ns=0,rip=0,rsp=0;
    std::size_t target_read_bytes=0,stack_bytes=0;
    std::size_t callback_calls=0,callback_bytes=0,stack_callback_bytes=0,module_callback_bytes=0;
    std::size_t callback_failures=0,budget_denials=0,unmapped_reads=0;
    bool seed_echo_skipped=false;
    std::size_t metadata_calls=0;
    bool stack_truncated=false;
    std::string capture_error,status,stop_reason;
    std::array<Frame,max_frames> frames{};
    std::size_t frame_count=0;
};
struct TerminalEvent {
    std::string capture_failure;
    bool thread_exit_observed=false,process_exit_observed=false;
    DWORD thread_exit_code=STILL_ACTIVE,child_exit_code=STILL_ACTIVE;
    CaptureApi api;
    SampleRecord sample;
};
struct RunReport {
    std::string status="failed",error;
    std::string dbghelp_error;
    bool disabled=false,sample_limit_reached=false,module_list_truncated=false;
    bool child_launched=false,job_assigned=false,initial_thread_resumed=false,child_exit_observed=false;
    std::uint32_t module_enumeration_attempts=0,module_enumeration_failures=0,watchdog_reason=0;
    std::uint32_t child_process_id=0,child_thread_id=0,parent_process_id=0,job_assignment_error=0;
    std::uint64_t child_creation_time=0;
    bool termination_attempted=false,termination_succeeded=false;
    std::uint32_t cleanup_wait_result=0,termination_error=0;
    std::uint64_t sampling_begin_elapsed_ms=0,duration_ms=0;
    bool report_truncated=false;
    std::size_t omitted_sample_records=0,omitted_module_records=0;
    std::uint64_t local_image_bytes=0;
    std::uint64_t child_exit_code=std::numeric_limits<std::uint64_t>::max();
    std::uint64_t cleanup_exit_code=std::numeric_limits<std::uint64_t>::max();
    bool cleanup_exit_observed=false;
    std::vector<Module> modules;
    std::vector<SampleRecord> samples;
    std::size_t sampling_attempts=0;
    std::vector<TerminalEvent> exit_race_events;
};

struct WatchState {
    HANDLE job=nullptr; // borrowed from the owning run
    std::atomic<bool> stop{false};
    std::atomic<std::uint32_t> reason{0}; // 1 global deadline, 2 suspended-pause deadline
    std::atomic<std::int64_t> suspended_since{0};
    std::atomic<bool> termination_attempted{false},termination_succeeded{false};
    std::atomic<DWORD> termination_error{0};
    std::int64_t frequency=0;
};

bool counter(std::int64_t& value) noexcept {LARGE_INTEGER out{};if(!QueryPerformanceCounter(&out))return false;value=out.QuadPart;return true;}
std::uint64_t elapsed_ns(std::int64_t begin,std::int64_t end,std::int64_t frequency) noexcept {
    if (frequency<=0 || end<begin) return 0;
    return static_cast<std::uint64_t>((static_cast<long double>(end-begin)*1000000000.0L)/frequency);
}

void watchdog_terminate(WatchState* state,DWORD code) noexcept {
    state->termination_attempted.store(true,std::memory_order_release);
    const BOOL terminated=TerminateJobObject(state->job,code);
    state->termination_succeeded.store(terminated!=FALSE,std::memory_order_release);
    if (!terminated) state->termination_error.store(GetLastError(),std::memory_order_release);
}

void watchdog_main(WatchState* state) noexcept {
    std::int64_t start=0;
    if (!counter(start) || state->frequency<=0) {state->reason.store(1);watchdog_terminate(state,124);return;}
    const auto deadline=start+state->frequency*child_deadline.count();
    const auto pause_limit=std::max<std::int64_t>(1,state->frequency*pause_deadline.count()/1000);
    while (!state->stop.load(std::memory_order_acquire)) {
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
        if (state->stop.load(std::memory_order_acquire)) break;
        std::int64_t now=0;
        if (!counter(now) || now>=deadline) {
            state->reason.store(1,std::memory_order_release);
            watchdog_terminate(state,124);
            break;
        }
        const auto paused=state->suspended_since.load(std::memory_order_acquire);
        if (paused && now>=paused && now-paused>pause_limit) {
            state->reason.store(2,std::memory_order_release);
            watchdog_terminate(state,125);
            break;
        }
    }
}

class Watchdog final {
    WatchState state_;
    std::thread thread_;
    RunReport* report_=nullptr;
public:
    explicit Watchdog(HANDLE job,RunReport* report=nullptr):state_{},report_(report) {
        state_.job=job;
        LARGE_INTEGER frequency{};
        if (!QueryPerformanceFrequency(&frequency) || frequency.QuadPart<=0) throw Failure("QueryPerformanceFrequency failed");
        state_.frequency=frequency.QuadPart;
        thread_=std::thread(watchdog_main,&state_);
    }
    Watchdog(const Watchdog&)=delete;Watchdog& operator=(const Watchdog&)=delete;
    ~Watchdog(){stop();}
    void pause_started(std::int64_t tick) noexcept {state_.suspended_since.store(tick,std::memory_order_release);}
    void pause_ended() noexcept {state_.suspended_since.store(0,std::memory_order_release);}
    [[nodiscard]] std::uint32_t reason() const noexcept {return state_.reason.load(std::memory_order_acquire);}
    [[nodiscard]] std::int64_t frequency() const noexcept {return state_.frequency;}
    void stop() noexcept {state_.stop.store(true,std::memory_order_release);if(thread_.joinable())thread_.join();if(report_){
        report_->watchdog_reason=reason();
        report_->termination_attempted=report_->termination_attempted||state_.termination_attempted.load();
        report_->termination_succeeded=report_->termination_succeeded||state_.termination_succeeded.load();
        if(state_.termination_error.load() && !report_->termination_error)report_->termination_error=state_.termination_error.load();
    }}
};

bool checked_image_range(std::uint32_t begin,std::uint32_t size,std::uint32_t image_size) noexcept {
    return size && begin<=image_size && size<=image_size-begin;
}

bool admitted_image_span(const Module& module,std::uint32_t rva,std::size_t bytes) noexcept {
    if (!module.image || !module.image_valid || !bytes || rva>module.size || bytes>module.size-rva) return false;
    bool covered=false;
    for (std::size_t i=0;i<module.readonly_count;++i) {
        const auto& range=module.readonly_ranges[i];
        if (rva>=range.begin && rva<=range.end && bytes<=range.end-rva) {covered=true;break;}
    }
    if (!covered) return false;
    const auto end=static_cast<std::uint64_t>(rva)+bytes;
    const auto found=std::lower_bound(module.blocked.begin(),module.blocked.end(),rva,
        [](const Range& a,std::uint32_t value){return a.end<=value;});
    return found==module.blocked.end() || found->begin>=end;
}

bool append_denied_span(Module& module,Range span) {
    if (!module.blocked.empty() && span.begin>=module.blocked.back().begin &&
        span.begin<=module.blocked.back().end) {
        module.blocked.back().end=std::max(module.blocked.back().end,span.end);
        return true;
    }
    if (module.blocked.size()>=65536) return false;
    module.blocked.push_back(span);return true;
}

void map_readonly_image(Module& module,std::uint64_t& total) {
    if (!module.size || module.size>max_image_bytes || module.size>max_total_image_bytes-total) {
        module.identity_error="module_image_capacity";return;
    }
    module.file.reset(CreateFileW(module.path.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_DELETE,
        nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr));
    if (!module.file) {module.identity_error="module_file_open_failed";return;}
    LARGE_INTEGER file_size{};
    if (!GetFileSizeEx(module.file.get(),&file_size) || file_size.QuadPart<0 ||
        static_cast<std::uint64_t>(file_size.QuadPart)>max_image_bytes) {
        module.identity_error="module_file_capacity";return;
    }
    module.file_bytes=static_cast<std::uint64_t>(file_size.QuadPart);
    alignas(16) std::array<unsigned char,4096> header{};
    DWORD header_bytes=0;
    if (!ReadFile(module.file.get(),header.data(),static_cast<DWORD>(header.size()),&header_bytes,nullptr) ||
        header_bytes<sizeof(IMAGE_DOS_HEADER)) {module.identity_error="module_header_read_failed";return;}
    const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(header.data());
    if (dos->e_magic!=IMAGE_DOS_SIGNATURE || dos->e_lfanew<0 ||
        static_cast<std::uint64_t>(dos->e_lfanew)+sizeof(IMAGE_NT_HEADERS64)>header_bytes) {
        module.identity_error="invalid_module_headers";return;
    }
    const auto* nt=reinterpret_cast<const IMAGE_NT_HEADERS64*>(header.data()+dos->e_lfanew);
    const auto section_offset=static_cast<std::uint64_t>(dos->e_lfanew)+
        offsetof(IMAGE_NT_HEADERS64,OptionalHeader)+nt->FileHeader.SizeOfOptionalHeader;
    if (nt->Signature!=IMAGE_NT_SIGNATURE || nt->FileHeader.Machine!=IMAGE_FILE_MACHINE_AMD64 ||
        nt->OptionalHeader.Magic!=IMAGE_NT_OPTIONAL_HDR64_MAGIC ||
        nt->FileHeader.SizeOfOptionalHeader!=sizeof(IMAGE_OPTIONAL_HEADER64) ||
        nt->OptionalHeader.NumberOfRvaAndSizes!=IMAGE_NUMBEROF_DIRECTORY_ENTRIES ||
        nt->OptionalHeader.SizeOfImage!=module.size ||
        nt->FileHeader.NumberOfSections==0 || nt->FileHeader.NumberOfSections>module.readonly_ranges.size() ||
        section_offset+sizeof(IMAGE_SECTION_HEADER)*nt->FileHeader.NumberOfSections>header_bytes) {
        module.identity_error="unsupported_module_image";return;
    }
    module.mapping.reset(CreateFileMappingW(module.file.get(),nullptr,PAGE_READONLY|SEC_IMAGE_NO_EXECUTE,0,0,nullptr));
    if (!module.mapping) {module.identity_error="module_image_mapping_failed";return;}
    module.image=MapViewOfFile(module.mapping.get(),FILE_MAP_READ,0,0,0);
    if (!module.image) {module.identity_error="module_image_view_failed";return;}
    total+=module.size;
    const auto* sections=reinterpret_cast<const IMAGE_SECTION_HEADER*>(header.data()+section_offset);
    for (std::size_t i=0;i<nt->FileHeader.NumberOfSections;++i) {
        const auto& section=sections[i];
        const auto extent=std::max(section.Misc.VirtualSize,section.SizeOfRawData);
        if (!extent || !(section.Characteristics&IMAGE_SCN_MEM_READ) || (section.Characteristics&IMAGE_SCN_MEM_WRITE) ||
            !checked_image_range(section.VirtualAddress,extent,module.size)) continue;
        module.readonly_ranges[module.readonly_count++]={section.VirtualAddress,section.VirtualAddress+extent};
    }
    module.image_valid=true;
    const auto* base=static_cast<const unsigned char*>(module.image);
    const auto& directories=nt->OptionalHeader.DataDirectory;
    const auto& reloc=directories[IMAGE_DIRECTORY_ENTRY_BASERELOC];
    if (reloc.Size) {
        if (!admitted_image_span(module,reloc.VirtualAddress,reloc.Size)) {
            module.identity_error="invalid_relocation_directory";module.image_valid=false;return;
        }
        std::size_t offset=0;
        while (offset<reloc.Size) {
            if (reloc.Size-offset<sizeof(IMAGE_BASE_RELOCATION)) {
                module.identity_error="truncated_relocation_block";module.image_valid=false;return;
            }
            const auto* block=reinterpret_cast<const IMAGE_BASE_RELOCATION*>(base+reloc.VirtualAddress+offset);
            if (block->SizeOfBlock<sizeof(IMAGE_BASE_RELOCATION) || block->SizeOfBlock>reloc.Size-offset ||
                block->SizeOfBlock%sizeof(WORD)) {
                module.identity_error="invalid_relocation_block";module.image_valid=false;return;
            }
            const auto entries=(block->SizeOfBlock-sizeof(IMAGE_BASE_RELOCATION))/sizeof(WORD);
            const auto* items=reinterpret_cast<const WORD*>(block+1);
            for (std::size_t i=0;i<entries;++i) {
                const WORD kind=items[i]>>12;
                if (kind==IMAGE_REL_BASED_ABSOLUTE) continue;
                const auto location=static_cast<std::uint64_t>(block->VirtualAddress)+(items[i]&0xfff);
                const DWORD extent=kind==IMAGE_REL_BASED_DIR64?8:kind==IMAGE_REL_BASED_HIGHLOW?4:0;
                if (!extent || location>module.size || extent>module.size-location) {
                    module.identity_error="unsupported_relocation_or_capacity";module.image_valid=false;return;
                }
                if (!append_denied_span(module,{static_cast<std::uint32_t>(location),static_cast<std::uint32_t>(location+extent)})) {
                    module.identity_error="relocation_span_capacity";module.image_valid=false;return;
                }
            }
            offset+=block->SizeOfBlock;
        }
    }
    const auto& iat=directories[IMAGE_DIRECTORY_ENTRY_IAT];
    if (iat.Size) {
        if (!checked_image_range(iat.VirtualAddress,iat.Size,module.size)) {
            module.identity_error="invalid_import_address_table";module.image_valid=false;return;
        }
        if (!append_denied_span(module,{iat.VirtualAddress,iat.VirtualAddress+iat.Size})) {
            module.identity_error="import_span_capacity";module.image_valid=false;return;
        }
    }
    std::sort(module.blocked.begin(),module.blocked.end(),[](const Range& a,const Range& b){return a.begin<b.begin;});
    std::vector<Range> merged;
    for (const auto& item:module.blocked) {
        if (!merged.empty() && item.begin<=merged.back().end) merged.back().end=std::max(merged.back().end,item.end);
        else merged.push_back(item);
    }
    module.blocked=std::move(merged);
    const auto& exception=directories[IMAGE_DIRECTORY_ENTRY_EXCEPTION];
    if (!exception.Size) {module.identity_error="module_has_no_exception_directory";return;}
    if (exception.Size%sizeof(IMAGE_RUNTIME_FUNCTION_ENTRY) ||
        exception.Size/sizeof(IMAGE_RUNTIME_FUNCTION_ENTRY)>65536 ||
        !admitted_image_span(module,exception.VirtualAddress,exception.Size)) {
        module.identity_error="invalid_exception_directory";return;
    }
    const auto* functions=reinterpret_cast<const IMAGE_RUNTIME_FUNCTION_ENTRY*>(base+exception.VirtualAddress);
    DWORD prior_end=0;
    for (std::size_t i=0;i<exception.Size/sizeof(IMAGE_RUNTIME_FUNCTION_ENTRY);++i) {
        const auto& f=functions[i];
        if (f.BeginAddress<prior_end || f.BeginAddress>=f.EndAddress || f.EndAddress>module.size ||
            !admitted_image_span(module,f.UnwindInfoAddress,4)) {
            module.identity_error="unsupported_runtime_function_table";return;
        }
        prior_end=f.EndAddress;
    }
    module.exception_rva=exception.VirtualAddress;module.exception_size=exception.Size;
}

void enumerate_modules(HANDLE process,std::vector<Module>& modules,std::uint32_t& attempts,
                       std::uint32_t& failures,bool& truncated,std::uint64_t& total) {
    modules.clear();attempts=0;failures=0;truncated=false;
    std::array<HMODULE,max_modules+1> handles{};
    DWORD needed=0;
    bool success=false;
    for (unsigned retry=0;retry<4;++retry) {
        ++attempts;
        needed=0;
        if (EnumProcessModulesEx(process,handles.data(),static_cast<DWORD>(sizeof(handles)),&needed,LIST_MODULES_ALL)) {
            success=true;
            break;
        }
        ++failures;
        if (retry<3) std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    if (!success) return;
    const std::size_t reported=needed/sizeof(HMODULE);
    const std::size_t count=std::min(reported,max_modules);
    truncated=reported>max_modules;
    for (std::size_t i=0;i<count;++i) {
        MODULEINFO info{};
        if (!GetModuleInformation(process,handles[i],&info,sizeof(info))) {++failures;continue;}
        std::array<wchar_t,max_path_chars> path{};
        const DWORD chars=GetModuleFileNameExW(process,handles[i],path.data(),static_cast<DWORD>(path.size()));
        Module module;
        module.handle=handles[i];module.base=reinterpret_cast<std::uintptr_t>(info.lpBaseOfDll);
        module.size=info.SizeOfImage;
        if (!chars || chars>=path.size()) {++failures;module.identity_error="module_path_failed_or_truncated";}
        else module.path.assign(path.data(),chars);
        if (!module.path.empty()) map_readonly_image(module,total);
        modules.push_back(std::move(module));
    }
}

bool readonly_module_read(const Module& module,std::uint32_t rva,std::size_t bytes,
                          unsigned char* output) noexcept {
    if (!admitted_image_span(module,rva,bytes)) return false;
    std::memcpy(output,static_cast<const unsigned char*>(module.image)+rva,bytes);
    return true;
}

struct WalkContext {
    std::uint64_t stack_base=0;
    const unsigned char* stack=nullptr;
    std::size_t stack_bytes=0;
    const std::vector<Module>* modules=nullptr;
    std::size_t callback_bytes=0,callback_stack_bytes=0,callback_module_bytes=0,callback_calls=0;
    std::size_t callback_failures=0,budget_denials=0,unmapped_reads=0,metadata_calls=0;
};
thread_local WalkContext* active_walk=nullptr;

BOOL CALLBACK snapshot_read_memory(HANDLE,DWORD64 address,PVOID output,DWORD bytes,LPDWORD read) {
    if (read) *read=0;
    auto* context=active_walk;
    if (!context) return FALSE;
    if (context->callback_calls>=max_callback_calls) {
        ++context->budget_denials;return FALSE;
    }
    ++context->callback_calls;
    if (!output || !read || !bytes) {++context->callback_failures;return FALSE;}
    if (context->callback_bytes>max_callback_read || bytes>max_callback_read-context->callback_bytes) {
        ++context->callback_failures;++context->budget_denials;return FALSE;
    }
    if (address>=context->stack_base && address-context->stack_base<=context->stack_bytes &&
        bytes<=context->stack_bytes-static_cast<std::size_t>(address-context->stack_base)) {
        std::memcpy(output,context->stack+static_cast<std::size_t>(address-context->stack_base),bytes);
        context->callback_bytes+=bytes;context->callback_stack_bytes+=bytes;*read=bytes;return TRUE;
    }
    if (context->modules) for (const auto& module:*context->modules) {
        if (address<module.base || address-module.base>=module.size) continue;
        const auto rva=static_cast<std::uint32_t>(address-module.base);
        if (readonly_module_read(module,rva,bytes,static_cast<unsigned char*>(output))) {
            context->callback_bytes+=bytes;context->callback_module_bytes+=bytes;*read=bytes;return TRUE;
        }
    }
    ++context->callback_failures;++context->unmapped_reads;
    return FALSE;
}

PVOID CALLBACK local_function_table(HANDLE,DWORD64 address_base) {
    if (!active_walk || !active_walk->modules) return nullptr;
    if (active_walk->metadata_calls>=max_callback_calls) {++active_walk->budget_denials;return nullptr;}
    ++active_walk->metadata_calls;
    for (const auto& module:*active_walk->modules) {
        if (address_base<module.base || address_base-module.base>=module.size || !module.image || !module.exception_rva ||
            !admitted_image_span(module,module.exception_rva,module.exception_size)) continue;
        const auto entries=module.exception_size/sizeof(IMAGE_RUNTIME_FUNCTION_ENTRY);
        const auto* functions=reinterpret_cast<const IMAGE_RUNTIME_FUNCTION_ENTRY*>(
            static_cast<const unsigned char*>(module.image)+module.exception_rva);
        const auto rva=static_cast<std::uint32_t>(address_base-module.base);
        std::size_t lo=0,hi=entries;
        while (lo<hi) {
            const auto mid=lo+(hi-lo)/2;
            const auto& item=functions[mid];
            if (item.BeginAddress<=rva) {
                lo=mid+1;
            } else hi=mid;
        }
        if (!lo) return nullptr;
        const auto& candidate=functions[lo-1];
        if (rva<candidate.BeginAddress || rva>=candidate.EndAddress) return nullptr;
        return const_cast<IMAGE_RUNTIME_FUNCTION_ENTRY*>(&candidate);
    }
    return nullptr;
}

DWORD64 CALLBACK local_module_base(HANDLE,DWORD64 address) {
    if (!active_walk || !active_walk->modules) return 0;
    if (active_walk->metadata_calls>=max_callback_calls) {++active_walk->budget_denials;return 0;}
    ++active_walk->metadata_calls;
    for (const auto& module:*active_walk->modules)
        if (address>=module.base && address-module.base<module.size) return module.base;
    return 0;
}

bool capture_stack_bytes(HANDLE process,Snapshot& sample) noexcept {
    std::uint64_t cursor=sample.rsp;
    std::uintptr_t stack_allocation=0;
    while (sample.stack_bytes<sample.stack.size()) {
        MEMORY_BASIC_INFORMATION region{};
        if (!VirtualQueryEx(process,reinterpret_cast<const void*>(static_cast<std::uintptr_t>(cursor)),
                            &region,sizeof(region))) {
            sample.capture_error="VirtualQueryEx_failed";sample.stack_truncated=true;return false;
        }
        if (!sample.stack_bytes) stack_allocation=reinterpret_cast<std::uintptr_t>(region.AllocationBase);
        const auto region_begin=reinterpret_cast<std::uintptr_t>(region.BaseAddress);
        if (region.RegionSize>std::numeric_limits<std::uintptr_t>::max()-region_begin ||
            cursor<region_begin || cursor>=region_begin+region.RegionSize || region.State!=MEM_COMMIT ||
            reinterpret_cast<std::uintptr_t>(region.AllocationBase)!=stack_allocation ||
            (region.Protect&(PAGE_GUARD|PAGE_NOACCESS))) {
            sample.capture_error="stack_region_unavailable";sample.stack_truncated=true;return false;
        }
        const auto region_end=static_cast<std::uint64_t>(region_begin+region.RegionSize);
        const auto remaining=sample.stack.size()-sample.stack_bytes;
        const auto amount=static_cast<std::size_t>(std::min<std::uint64_t>(remaining,region_end-cursor));
        if (!amount) {sample.capture_error="empty_stack_region";sample.stack_truncated=true;return false;}
        SIZE_T copied=0;
        const BOOL ok=ReadProcessMemory(process,reinterpret_cast<const void*>(static_cast<std::uintptr_t>(cursor)),
            sample.stack.data()+sample.stack_bytes,amount,&copied);
        if (copied>amount || copied>max_target_read-sample.target_read_bytes) {
            sample.capture_error="target_read_bound_violation";sample.stack_truncated=true;return false;
        }
        sample.stack_bytes+=copied;sample.target_read_bytes+=copied;cursor+=copied;
        if (!ok || copied!=amount) {
            sample.capture_error="ReadProcessMemory_partial_or_failed";sample.stack_truncated=true;return false;
        }
    }
    sample.stack_truncated=sample.stack_bytes==sample.stack.size();
    if (sample.stack_truncated) sample.capture_error="stack_capture_cap";
    return true;
}

bool capture_snapshot(HANDLE process,HANDLE thread,Watchdog& watchdog,Snapshot& sample,
                      const char*& failure) noexcept {
    sample.api.suspend_called=true;
    DWORD previous=SuspendThread(thread);sample.api.suspend_return=previous;
    if (previous==DWORD(-1)) {sample.api.suspend_error=GetLastError();failure="SuspendThread_failed";return false;}
    std::int64_t pause_begin=0;
    const bool have_counter=counter(pause_begin);
    if (have_counter) watchdog.pause_started(pause_begin);
    bool captured=true;
    if (previous!=0) {
        sample.api.resume_called=true;
        const DWORD restored=ResumeThread(thread);sample.api.resume_return=restored;
        if (restored==DWORD(-1)) sample.api.resume_error=GetLastError();
        watchdog.pause_ended();
        if (have_counter) {std::int64_t end=0;if(counter(end))sample.pause_ns=elapsed_ns(pause_begin,end,watchdog.frequency());}
        failure=restored==DWORD(-1)?"unexpected_suspend_count_restore_failed":"unexpected_prior_suspend_count";
        return false;
    }
    if (!have_counter) {sample.non_api_error=true;failure="QueryPerformanceCounter_failed_during_pause";captured=false;}
    else {
        sample.context={};sample.context.ContextFlags=CONTEXT_FULL;
        sample.api.context_called=true;
        sample.api.context_succeeded=GetThreadContext(thread,&sample.context)!=FALSE;
        if (!sample.api.context_succeeded) {sample.api.context_error=GetLastError();failure="GetThreadContext_failed";captured=false;}
        else {
            sample.rip=sample.context.Rip;sample.rsp=sample.context.Rsp;sample.rbp=sample.context.Rbp;
            if (!capture_stack_bytes(process,sample)) captured=true; // retain an explicit partial snapshot
        }
    }
    sample.api.resume_called=true;
    const DWORD restored=ResumeThread(thread);sample.api.resume_return=restored;
    if (restored==DWORD(-1)) sample.api.resume_error=GetLastError();
    if (have_counter) {
        std::int64_t end=0;
        if (counter(end)) sample.pause_ns=elapsed_ns(pause_begin,end,watchdog.frequency());
        else {sample.non_api_error=true;sample.capture_error="QueryPerformanceCounter_failed_after_resume";if(captured)failure="QueryPerformanceCounter_failed_after_resume";captured=false;}
    }
    watchdog.pause_ended();
    if (restored==DWORD(-1)) {failure="ResumeThread_failed";return false;}
    if (restored!=1) {failure="owned_suspend_increment_changed";return false;}
    if (watchdog.reason()==2) {failure="suspended_pause_watchdog_fired";return false;}
    return captured;
}

bool terminal_capture_allowed(const Snapshot& sample,const char* failure,std::uint32_t watchdog_reason) noexcept {
    if (sample.non_api_error || sample.pause_ns>250000000 || watchdog_reason) return false;
    const auto& api=sample.api;
    const std::string_view reason(failure);
    if (!api.suspend_called) return false;
    if (reason=="SuspendThread_failed")
        return api.suspend_return==DWORD(-1) && !api.context_called && !api.resume_called;
    if (api.suspend_return!=0 || !api.context_called || !api.resume_called) return false;
    if (reason=="GetThreadContext_failed")
        return !api.context_succeeded && api.resume_return==1;
    if (reason=="ResumeThread_failed")
        return api.resume_return==DWORD(-1);
    return reason=="owned_suspend_increment_changed" && api.resume_return==0;
}

bool collect_terminal_event(HANDLE process,HANDLE thread,Watchdog& watchdog,const Snapshot& snapshot,
                            const char* failure,const SampleRecord& record,RunReport& report) {
    if (!terminal_capture_allowed(snapshot,failure,watchdog.reason()) || !report.exit_race_events.empty())
        return false;
    // The kernel can reject a capture after thread teardown starts, before the
    // two handles become signaled. Observe only this existing child and never
    // attempt another capture. The watchdog remains active during the wait.
    const std::array<HANDLE,2> owned_handles{thread,process};
    if (WaitForMultipleObjects(static_cast<DWORD>(owned_handles.size()),owned_handles.data(),
                               TRUE,terminal_exit_observation_ms)!=WAIT_OBJECT_0)
        return false;
    DWORD thread_exit=STILL_ACTIVE,process_exit=STILL_ACTIVE;
    if (!GetExitCodeThread(thread,&thread_exit) || !GetExitCodeProcess(process,&process_exit)) return false;
    report.child_exit_observed=true;report.child_exit_code=process_exit;
    if (thread_exit!=0 || process_exit!=0 || watchdog.reason()) return false;
    TerminalEvent event;
    event.capture_failure=failure;
    event.thread_exit_observed=true;event.process_exit_observed=true;
    event.thread_exit_code=thread_exit;event.child_exit_code=process_exit;
    event.api=snapshot.api;event.sample=record;event.sample.status="terminal_race_capture";
    report.exit_race_events.push_back(std::move(event));
    return true;
}

std::atomic<std::uint64_t> session_serial{1};
HANDLE synthetic_token(HANDLE process,HANDLE thread) noexcept {
    for (;;) {
        const auto serial=session_serial.fetch_add(1,std::memory_order_relaxed)&0x0000ffffffffffffULL;
        const auto raw=static_cast<std::uintptr_t>(0x7ffe000000000000ULL|(serial<<1)|1ULL);
        const auto token=reinterpret_cast<HANDLE>(raw);
        if (token!=process && token!=thread && token!=INVALID_HANDLE_VALUE) return token;
    }
}

BOOL CALLBACK dbghelp_memory_callback(HANDLE,DWORD action,ULONG64 callback_data,ULONG64) {
    if (action!=CBA_READ_MEMORY) return TRUE;
    auto* request=reinterpret_cast<IMAGEHLP_CBA_READ_MEMORY*>(callback_data);
    if (!request) return FALSE;
    DWORD copied=0;
    const BOOL ok=snapshot_read_memory(nullptr,request->addr,request->buf,request->bytes,&copied);
    if (request->bytesread) *request->bytesread=copied;
    return ok;
}

struct DbgSession {
    HANDLE token=nullptr,thread_token=nullptr;
    bool initialized=false;
    std::string error;
    DbgSession(HANDLE process,HANDLE thread,const std::wstring& symbol_path,const std::vector<Module>& modules)
        :token(synthetic_token(process,thread)),thread_token(synthetic_token(process,thread)) {
        SymSetOptions(SYMOPT_DEFERRED_LOADS|SYMOPT_FAIL_CRITICAL_ERRORS|SYMOPT_NO_PROMPTS);
        if (!SymInitializeW(token,symbol_path.c_str(),FALSE)) {error="SymInitialize_failed";return;}
        initialized=true;
        if (!SymRegisterCallback64(token,&dbghelp_memory_callback,0)) error="SymRegisterCallback64_failed";
        for (const auto& module:modules) {
            if (module.path.empty() || !module.image_valid || !module.image) continue;
            if (!SymLoadModuleExW(token,module.file.get(),module.path.c_str(),nullptr,module.base,module.size,nullptr,SLMFLAG_NO_SYMBOLS)) {
                if (!error.empty()) error.push_back(';');
                error+="SymLoadModuleEx_failed";
            }
        }
    }
    ~DbgSession(){if(initialized)SymCleanup(token);}
};

WalkResult walk_snapshot(const Snapshot& sample,const std::vector<Module>& modules,DbgSession& session) noexcept {
    WalkResult result;
    if (!session.initialized || !sample.rip || !sample.stack_bytes) {
        result.stop_reason=!session.initialized?"dbghelp_unavailable":!sample.rip?"zero_seed_rip":"no_captured_stack";
        return result;
    }
    WalkContext context{sample.rsp,sample.stack.data(),sample.stack_bytes,&modules};
    active_walk=&context;
    STACKFRAME64 frame{};
    frame.AddrPC.Offset=sample.context.Rip;frame.AddrPC.Mode=AddrModeFlat;
    frame.AddrFrame.Offset=sample.context.Rbp;frame.AddrFrame.Mode=AddrModeFlat;
    frame.AddrStack.Offset=sample.context.Rsp;frame.AddrStack.Mode=AddrModeFlat;
    CONTEXT copy=sample.context;
    DWORD64 prior_pc=sample.context.Rip,prior_sp=sample.context.Rsp;
    for (std::size_t attempt=0;attempt<max_frames+1;++attempt) {
        const auto lookup_pc=prior_pc-(result.count?1:0);
        const Module* current=nullptr;
        for (const auto& candidate:modules) {
            if (lookup_pc>=candidate.base && lookup_pc-candidate.base<candidate.size) {current=&candidate;break;}
        }
        if (!current) {result.stop_reason="unmapped_current_frame";break;}
        if (!current->image_valid || (!current->exception_rva &&
            current->identity_error!="module_has_no_exception_directory")) {
            result.stop_reason="unsupported_current_frame_metadata";break;
        }
        const BOOL ok=StackWalk64(IMAGE_FILE_MACHINE_AMD64,session.token,session.thread_token,
            &frame,&copy,&snapshot_read_memory,&local_function_table,&local_module_base,nullptr);
        if (!ok) {result.stop_reason="stackwalk_returned_false";break;}
        const auto pc=frame.AddrPC.Offset,sp=frame.AddrStack.Offset;
        if (!pc) {result.stop_reason="zero_pc";break;}
        if (attempt==0 && pc==sample.rip && sp==sample.rsp) {result.seed_echo_skipped=true;continue;}
        if (sp<=prior_sp) {result.stop_reason="nonprogressing_stack_pointer";break;}
        bool repeated=false;
        for (std::size_t i=0;i<result.count;++i)
            if (result.frames[i].pc==pc && result.frames[i].sp==sp) {repeated=true;break;}
        if (repeated || (pc==prior_pc && sp==prior_sp)) {result.stop_reason="repeated_pc_sp";break;}
        result.frames[result.count++]={pc,sp};
        prior_pc=pc;prior_sp=sp;
        if (result.count==max_frames) {result.stop_reason="frame_cap";break;}
    }
    active_walk=nullptr;
    result.callback_calls=context.callback_calls;result.callback_bytes=context.callback_bytes;
    result.stack_callback_bytes=context.callback_stack_bytes;result.module_callback_bytes=context.callback_module_bytes;
    result.callback_failures=context.callback_failures;result.budget_denials=context.budget_denials;
    result.unmapped_reads=context.unmapped_reads;result.metadata_calls=context.metadata_calls;
    if (result.budget_denials) result.stop_reason="callback_budget:"+result.stop_reason;
    if (result.count==0) result.stop_reason="partial_rip_only:"+result.stop_reason;
    return result;
}

struct Child final {
    Handle job,process,thread;
    RunReport* report=nullptr;
    DWORD process_id=0;
    bool job_assigned=false,initial_thread_resumed=false,exit_observed=false;
    DWORD observed_exit_code=STILL_ACTIVE,cleanup_exit_code=STILL_ACTIVE;
    bool cleanup_exit_observed=false;
    Child()=default;
    Child(const Child&)=delete;Child& operator=(const Child&)=delete;
    Child(Child&&)=default;Child& operator=(Child&&)=default;
    ~Child(){
        if (!process) return;
        DWORD wait=WaitForSingleObject(process.get(),0);
        if (wait!=WAIT_OBJECT_0) {
            if (report) report->termination_attempted=true;
            const BOOL ended=job && job_assigned?TerminateJobObject(job.get(),127):TerminateProcess(process.get(),126);
            if (report) {
                report->termination_succeeded=ended!=FALSE;
                if (!ended) report->termination_error=GetLastError();
            }
            wait=WaitForSingleObject(process.get(),5000);
        }
        if (report) {
            report->cleanup_wait_result=wait;
            if (wait==WAIT_OBJECT_0) {
                DWORD exit=STILL_ACTIVE;
                if (GetExitCodeProcess(process.get(),&exit)) {
                    report->cleanup_exit_observed=true;report->cleanup_exit_code=exit;
                }
            }
        }
    }
};

Child launch_child(const Options& options,RunReport& report,bool force_assignment_failure=false) {
    Child child;child.report=&report;
    child.job.reset(CreateJobObjectW(nullptr,nullptr));
    if (!child.job) throw Failure("CreateJobObject_failed");
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!SetInformationJobObject(child.job.get(),JobObjectExtendedLimitInformation,&limits,sizeof(limits)))
        throw Failure("SetInformationJobObject_failed");
    std::array<Handle,3> inherited;
    std::array<HANDLE,3> listed{};
    const std::array<DWORD,3> kinds{STD_INPUT_HANDLE,STD_OUTPUT_HANDLE,STD_ERROR_HANDLE};
    for (std::size_t i=0;i<kinds.size();++i) {
        const HANDLE source=GetStdHandle(kinds[i]);
        if (!source || source==INVALID_HANDLE_VALUE ||
            !DuplicateHandle(GetCurrentProcess(),source,GetCurrentProcess(),&listed[i],0,TRUE,DUPLICATE_SAME_ACCESS))
            throw Failure("standard_handle_duplicate_failed");
        inherited[i].reset(listed[i]);
    }
    SIZE_T attribute_bytes=0;
    InitializeProcThreadAttributeList(nullptr,1,0,&attribute_bytes);
    if (!attribute_bytes) throw Failure("attribute_list_size_failed");
    std::vector<std::max_align_t> attribute_storage((attribute_bytes+sizeof(std::max_align_t)-1)/sizeof(std::max_align_t));
    auto* attributes=reinterpret_cast<PPROC_THREAD_ATTRIBUTE_LIST>(attribute_storage.data());
    if (!InitializeProcThreadAttributeList(attributes,1,0,&attribute_bytes)) throw Failure("InitializeProcThreadAttributeList_failed");
    const auto delete_attributes=[&]{DeleteProcThreadAttributeList(attributes);};
    if (!UpdateProcThreadAttribute(attributes,0,PROC_THREAD_ATTRIBUTE_HANDLE_LIST,listed.data(),sizeof(listed),nullptr,nullptr)) {
        delete_attributes();throw Failure("UpdateProcThreadAttribute_handle_list_failed");
    }
    STARTUPINFOEXW startup{};startup.StartupInfo.cb=sizeof(startup);startup.lpAttributeList=attributes;
    startup.StartupInfo.dwFlags=STARTF_USESTDHANDLES;
    startup.StartupInfo.hStdInput=listed[0];startup.StartupInfo.hStdOutput=listed[1];startup.StartupInfo.hStdError=listed[2];
    std::wstring command=quote_argument(options.child)+L" "+quote_argument(options.scratch);
    PROCESS_INFORMATION process{};
    const BOOL created=CreateProcessW(options.child.c_str(),command.data(),nullptr,nullptr,TRUE,
        CREATE_SUSPENDED|EXTENDED_STARTUPINFO_PRESENT|CREATE_UNICODE_ENVIRONMENT,
        nullptr,nullptr,&startup.StartupInfo,&process);
    delete_attributes();
    if (!created) throw Failure("CreateProcess_suspended_failed");
    child.process.reset(process.hProcess);child.thread.reset(process.hThread);child.process_id=process.dwProcessId;
    report.child_launched=true;report.child_process_id=child.process_id;
    report.child_thread_id=process.dwThreadId;report.parent_process_id=GetCurrentProcessId();
    FILETIME created_time{},exited_time{},kernel_time{},user_time{};
    if (!GetProcessTimes(child.process.get(),&created_time,&exited_time,&kernel_time,&user_time))
        throw Failure("GetProcessTimes_creation_identity_failed");
    report.child_creation_time=(static_cast<std::uint64_t>(created_time.dwHighDateTime)<<32)|created_time.dwLowDateTime;
    USHORT process_machine=0,native_machine=0;
    if (!IsWow64Process2(child.process.get(),&process_machine,&native_machine))
        throw Failure("IsWow64Process2_failed");
    if (process_machine!=IMAGE_FILE_MACHINE_UNKNOWN || native_machine!=IMAGE_FILE_MACHINE_AMD64)
        throw Failure("unsupported_child_architecture");
    if (force_assignment_failure || !AssignProcessToJobObject(child.job.get(),child.process.get())) {
        const DWORD error=force_assignment_failure?ERROR_ACCESS_DENIED:GetLastError();
        report.job_assignment_error=error;
        throw Failure((std::string("AssignProcessToJobObject_failed_")+std::to_string(error)).c_str());
    }
    child.job_assigned=true;
    report.job_assigned=true;
    return child;
}


int run_child(const Options& options,RunReport& report,bool force_assignment_failure=false,bool force_terminal_race=false) {
    report.disabled=options.disabled;
    Child child=launch_child(options,report,force_assignment_failure);
    Watchdog watchdog(child.job.get(),&report);
    const auto began=std::chrono::steady_clock::now();
    const DWORD first_resume=ResumeThread(child.thread.get());
    if (first_resume==DWORD(-1) || first_resume!=1) throw Failure("initial_ResumeThread_failed_or_unexpected_count");
    child.initial_thread_resumed=true;report.initial_thread_resumed=true;

    std::unique_ptr<DbgSession> symbols;
    if (!options.disabled) {
        (void)WaitForSingleObject(child.process.get(),20);
        enumerate_modules(child.process.get(),report.modules,report.module_enumeration_attempts,
            report.module_enumeration_failures,report.module_list_truncated,report.local_image_bytes);
        symbols=std::make_unique<DbgSession>(child.process.get(),child.thread.get(),options.symbols,report.modules);
        report.dbghelp_error=symbols->error;
    }
    report.sampling_begin_elapsed_ms=static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-began).count());
    bool child_exited=false;
    while (!child_exited) {
        // Test-only injection models a timeout immediately before natural exit.
        const DWORD wait=force_terminal_race && report.sampling_attempts==0?WAIT_TIMEOUT:
            WaitForSingleObject(child.process.get(),options.interval_ms);
        if (wait==WAIT_OBJECT_0) {child_exited=true;break;}
        if (wait!=WAIT_TIMEOUT) throw Failure("WaitForSingleObject_child_failed");
        if (watchdog.reason()) throw Failure(watchdog.reason()==1?"child_watchdog_deadline":"pause_watchdog_deadline");
        if (options.disabled || report.samples.size()>=max_samples) {
            if (!options.disabled) report.sample_limit_reached=true;
            continue;
        }
        if (force_terminal_race && report.sampling_attempts==0 &&
            WaitForSingleObject(child.process.get(),5000)!=WAIT_OBJECT_0)
            throw Failure("forced_terminal_race_child_did_not_exit");
        ++report.sampling_attempts;
        Snapshot snapshot;
        const char* capture_failure="";
        const bool captured=capture_snapshot(child.process.get(),child.thread.get(),watchdog,snapshot,capture_failure);
        WalkResult walk;
        if (symbols && captured) walk=walk_snapshot(snapshot,report.modules,*symbols);
        SampleRecord record;record.api=snapshot.api;
        record.elapsed_ms=static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now()-began).count());
        record.pause_ns=snapshot.pause_ns;record.rip=snapshot.rip;record.rsp=snapshot.rsp;
        record.target_read_bytes=snapshot.target_read_bytes;record.stack_bytes=snapshot.stack_bytes;
        record.stack_truncated=snapshot.stack_truncated;record.capture_error=snapshot.capture_error;
        record.callback_calls=walk.callback_calls;record.callback_bytes=walk.callback_bytes;
        record.stack_callback_bytes=walk.stack_callback_bytes;record.module_callback_bytes=walk.module_callback_bytes;
        record.callback_failures=walk.callback_failures;record.budget_denials=walk.budget_denials;record.unmapped_reads=walk.unmapped_reads;
        record.status=walk.count?"partial_unwind":"partial_rip_only";
        if (options.disabled) record.status="disabled";
        record.stop_reason=walk.stop_reason;
        record.frames=walk.frames;record.frame_count=walk.count;
        record.seed_echo_skipped=walk.seed_echo_skipped;record.metadata_calls=walk.metadata_calls;
        if (record.target_read_bytes>max_target_read || record.callback_bytes>max_callback_read ||
            record.frame_count>max_frames) throw Failure("sample_bound_violation");
        if (!captured && collect_terminal_event(child.process.get(),child.thread.get(),watchdog,snapshot,
                                                capture_failure,record,report)) {
            child_exited=true;break;
        }
        report.samples.push_back(std::move(record));
        if (!captured) throw Failure(!capture_failure[0]?"snapshot_capture_failed":capture_failure);
        if (snapshot.pause_ns>250000000) throw Failure("sample_pause_deadline_exceeded");
    }
    watchdog.stop();
    report.watchdog_reason=watchdog.reason();
    if (report.watchdog_reason) throw Failure(report.watchdog_reason==1?"child_watchdog_deadline":"pause_watchdog_deadline");
    DWORD exit_code=STILL_ACTIVE;
    if (!GetExitCodeProcess(child.process.get(),&exit_code)) throw Failure("GetExitCodeProcess_failed");
    child.exit_observed=true;child.observed_exit_code=exit_code;report.child_exit_observed=true;
    report.child_exit_code=exit_code;
    report.duration_ms=static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-began).count());
    if (exit_code!=0) {report.status="child_failed";report.error="child_exit_code_nonzero";return 4;}
    report.status=options.disabled?"completed_disabled":report.samples.empty()?"completed_no_samples":"completed_partial_unwinds";
    return 0;
}

void append_module(Json& json,const Module& module) {
    json.raw("{\"base\":");json.quoted(hex64(module.base));
    json.raw(",\"size\":");json.raw(std::to_string(module.size));
    json.raw(",\"path\":");json.quoted(wide_to_utf8(module.path));
    json.raw(",\"mapped_local_image\":");json.raw(module.image?"true":"false");
    json.raw(",\"exception_directory\":");json.raw(module.exception_rva?"true":"false");
    json.raw(",\"image_usable\":");json.raw(module.image_valid?"true":"false");
    json.raw(",\"file_bytes\":");json.raw(std::to_string(module.file_bytes));
    json.raw(",\"denied_image_spans\":");json.raw(std::to_string(module.blocked.size()));
    json.raw(",\"identity_error\":");json.quoted(module.identity_error);json.raw("}");
}

void append_api(Json& json,const CaptureApi& api) {
    json.raw("{\"suspend_return\":");json.raw(api.suspend_called?std::to_string(api.suspend_return):"null");
    json.raw(",\"suspend_error\":");json.raw(std::to_string(api.suspend_error));
    json.raw(",\"context_result\":");json.raw(api.context_called?(api.context_succeeded?"true":"false"):"null");
    json.raw(",\"context_error\":");json.raw(std::to_string(api.context_error));
    json.raw(",\"resume_return\":");json.raw(api.resume_called?std::to_string(api.resume_return):"null");
    json.raw(",\"resume_error\":");json.raw(std::to_string(api.resume_error));json.raw("}");
}

void append_sample(Json& json,const SampleRecord& sample) {
    json.raw("{\"elapsed_ms\":");json.raw(std::to_string(sample.elapsed_ms));
    json.raw(",\"api_outcomes\":");append_api(json,sample.api);
    json.raw(",\"pause_ns\":");json.raw(std::to_string(sample.pause_ns));
    json.raw(",\"seed_rip\":");json.quoted(hex64(sample.rip));
    json.raw(",\"seed_rsp\":");json.quoted(hex64(sample.rsp));
    json.raw(",\"target_read_bytes\":");json.raw(std::to_string(sample.target_read_bytes));
    json.raw(",\"captured_stack_bytes\":");json.raw(std::to_string(sample.stack_bytes));
    json.raw(",\"stack_capture_truncated\":");json.raw(sample.stack_truncated?"true":"false");
    json.raw(",\"capture_error\":");json.quoted(sample.capture_error);
    json.raw(",\"callback_calls\":");json.raw(std::to_string(sample.callback_calls));
    json.raw(",\"callback_bytes\":");json.raw(std::to_string(sample.callback_bytes));
    json.raw(",\"stack_callback_bytes\":");json.raw(std::to_string(sample.stack_callback_bytes));
    json.raw(",\"module_callback_bytes\":");json.raw(std::to_string(sample.module_callback_bytes));
    json.raw(",\"callback_failures\":");json.raw(std::to_string(sample.callback_failures));
    json.raw(",\"budget_denials\":");json.raw(std::to_string(sample.budget_denials));
    json.raw(",\"unmapped_reads\":");json.raw(std::to_string(sample.unmapped_reads));
    json.raw(",\"metadata_calls\":");json.raw(std::to_string(sample.metadata_calls));
    json.raw(",\"seed_echo_skipped\":");json.raw(sample.seed_echo_skipped?"true":"false");
    json.raw(",\"status\":");json.quoted(sample.status);
    json.raw(",\"stop_reason\":");json.quoted(sample.stop_reason);
    json.raw(",\"frames\":[");
    for (std::size_t i=0;i<sample.frame_count;++i) {
        if (i) json.raw(",");
        json.raw("{\"pc\":");json.quoted(hex64(sample.frames[i].pc));
        json.raw(",\"sp\":");json.quoted(hex64(sample.frames[i].sp));json.raw("}");
    }
    json.raw("]}");
}

void append_terminal_event(Json& json,const TerminalEvent& event) {
    json.raw("{\"capture_failure\":");json.quoted(event.capture_failure);
    json.raw(",\"thread_exit_observed\":");json.raw(event.thread_exit_observed?"true":"false");
    json.raw(",\"thread_exit_code\":");json.raw(std::to_string(event.thread_exit_code));
    json.raw(",\"process_exit_observed\":");json.raw(event.process_exit_observed?"true":"false");
    json.raw(",\"child_exit_code\":");json.raw(std::to_string(event.child_exit_code));
    json.raw(",\"api_outcomes\":");append_api(json,event.api);
    json.raw(",\"sample\":");append_sample(json,event.sample);json.raw("}");
}

std::string build_report(const Options& options,const RunReport& report) {
    Json json;
    json.raw("{\"schema_version\":1,\"sampler\":\"owned-child-stack-sample-v1\",\"architecture\":\"windows-x64\"");
    json.raw(",\"mode\":");json.quoted(report.disabled?"disabled":"periodic_stack_observation");
    json.raw(",\"interval_ms\":");json.raw(std::to_string(options.interval_ms));
    json.raw(",\"child\":");json.quoted(wide_to_utf8(options.child));
    json.raw(",\"scratch\":");json.quoted(wide_to_utf8(options.scratch));
    json.raw(",\"symbols_directory\":");json.quoted(wide_to_utf8(options.symbols));
    json.raw(",\"status\":");json.quoted(report.status);
    json.raw(",\"error\":");json.quoted(report.error);
    json.raw(",\"child_exit_code\":");
    if (report.child_exit_code==std::numeric_limits<std::uint64_t>::max()) json.raw("null");
    else json.raw(std::to_string(report.child_exit_code));
    json.raw(",\"watchdog_reason\":");json.raw(std::to_string(report.watchdog_reason));
    json.raw(",\"sample_limit_reached\":");json.raw(report.sample_limit_reached?"true":"false");
    json.raw(",\"module_list_truncated\":");json.raw(report.module_list_truncated?"true":"false");
    json.raw(",\"module_enumeration_attempts\":");json.raw(std::to_string(report.module_enumeration_attempts));
    json.raw(",\"module_enumeration_failures\":");json.raw(std::to_string(report.module_enumeration_failures));
    json.raw(",\"report_truncated\":");json.raw(report.report_truncated?"true":"false");
    json.raw(",\"omitted_sample_records\":");json.raw(std::to_string(report.omitted_sample_records));
    json.raw(",\"omitted_module_records\":");json.raw(std::to_string(report.omitted_module_records));
    json.raw(",\"dbghelp_error\":");json.quoted(report.dbghelp_error);
    json.raw(",\"child_launched\":");json.raw(report.child_launched?"true":"false");
    json.raw(",\"child_process_id\":");json.raw(std::to_string(report.child_process_id));
    json.raw(",\"child_thread_id\":");json.raw(std::to_string(report.child_thread_id));
    json.raw(",\"parent_process_id\":");json.raw(std::to_string(report.parent_process_id));
    json.raw(",\"child_creation_time\":");json.raw(std::to_string(report.child_creation_time));
    json.raw(",\"job_assigned\":");json.raw(report.job_assigned?"true":"false");
    json.raw(",\"job_assignment_error\":");json.raw(std::to_string(report.job_assignment_error));
    json.raw(",\"initial_thread_resumed\":");json.raw(report.initial_thread_resumed?"true":"false");
    json.raw(",\"child_exit_observed\":");json.raw(report.child_exit_observed?"true":"false");
    json.raw(",\"cleanup_exit_observed\":");json.raw(report.cleanup_exit_observed?"true":"false");
    json.raw(",\"cleanup_exit_code\":");json.raw(report.cleanup_exit_observed?std::to_string(report.cleanup_exit_code):"null");
    json.raw(",\"cleanup_wait_result\":");json.raw(std::to_string(report.cleanup_wait_result));
    json.raw(",\"termination_attempted\":");json.raw(report.termination_attempted?"true":"false");
    json.raw(",\"termination_succeeded\":");json.raw(report.termination_succeeded?"true":"false");
    json.raw(",\"termination_error\":");json.raw(std::to_string(report.termination_error));
    json.raw(",\"local_image_bytes\":");json.raw(std::to_string(report.local_image_bytes));
    json.raw(",\"sampling_begin_elapsed_ms\":");json.raw(std::to_string(report.sampling_begin_elapsed_ms));
    json.raw(",\"duration_ms\":");json.raw(std::to_string(report.duration_ms));
    json.raw(",\"modules\":[");
    for (std::size_t i=0;i<report.modules.size();++i) {if(i)json.raw(",");append_module(json,report.modules[i]);}
    json.raw("],\"sampling_attempts\":");json.raw(std::to_string(report.sampling_attempts));
    json.raw(",\"exit_race_events\":[");
    for (std::size_t i=0;i<report.exit_race_events.size();++i) {if(i)json.raw(",");append_terminal_event(json,report.exit_race_events[i]);}
    json.raw("],\"samples\":[");
    for (std::size_t i=0;i<report.samples.size();++i) {if(i)json.raw(",");append_sample(json,report.samples[i]);}
    json.raw("]}");
    return json.str();
}

void write_new_report(const std::wstring& path,const std::string& content) {
    if (content.size()>max_report_bytes) throw Failure("report exceeds 4 MiB cap");
    Handle file(CreateFileW(path.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr));
    if (!file) throw Failure("report_create_new_failed");
    std::size_t offset=0;
    while (offset<content.size()) {
        const DWORD amount=static_cast<DWORD>(std::min<std::size_t>(content.size()-offset,1u<<20));
        DWORD written=0;
        if (!WriteFile(file.get(),content.data()+offset,amount,&written,nullptr) || !written) {
            file.reset();throw Failure("report_write_failed_partial_preserved");
        }
        offset+=written;
    }
    if (!FlushFileBuffers(file.get())) {file.reset();throw Failure("report_flush_failed_partial_preserved");}
}

std::string serialize_report(const Options& options,RunReport& report,int& result) {
    std::string json;
    try {json=build_report(options,report);}
    catch (const std::exception&) {
        report.status="failed";report.error="report_serialization_failed";
        report.report_truncated=true;
        report.omitted_sample_records=report.samples.size();
        report.omitted_module_records=report.modules.size();
        report.samples.clear();report.modules.clear();
        json=build_report(options,report);
        result=2;
    }
    return json;
}

int execute(const Options& options,bool force_assignment_failure=false,bool force_terminal_race=false) {
    validate_options(options);
    RunReport report;
    report.disabled=options.disabled;
    int result=2;
    try {result=run_child(options,report,force_assignment_failure,force_terminal_race);}
    catch (const std::exception& error) {report.status="failed";report.error=error.what();}
    const auto json=serialize_report(options,report,result);
    write_new_report(options.report,json);
    return result;
}

} // namespace owned_child_stack_sample

int wmain(int argc,wchar_t** argv) {
    using namespace owned_child_stack_sample;
    try {
        const auto options=parse_options(argc,argv);
        return execute(options);
    } catch (const std::exception& error) {
        std::fwprintf(stderr,L"owned-child-stack-sample: %S\n",error.what());
        return 2;
    }
}

#else
#include <cstdio>
int main() {
    std::fputs("owned-child-stack-sample unsupported: requires Windows x64; no child was launched\n",stderr);
    return 2;
}
#endif
