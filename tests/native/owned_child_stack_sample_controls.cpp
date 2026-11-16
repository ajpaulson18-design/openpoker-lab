#define wmain owned_child_stack_sample_cli_wmain
#include "../../native/owned_child_stack_sample.cpp"
#undef wmain

#if defined(_WIN32) && defined(_WIN64) && (defined(_M_X64) || defined(__x86_64__))
#include <cstdio>
#include <fstream>
#include <iterator>

namespace {
using namespace owned_child_stack_sample;

void control_require(bool value,const char* message) {
    if (!value) throw Failure(message);
}

std::wstring current_executable() {
    std::wstring path(32768,L'\0');
    const DWORD count=GetModuleFileNameW(nullptr,path.data(),static_cast<DWORD>(path.size()));
    if (!count || count>=path.size()) throw Failure("controls cannot locate their executable");
    path.resize(count);return path;
}

__declspec(noinline) std::uint64_t fixture_hot_leaf(std::uint64_t until) {
    volatile std::uint64_t value=0x10001;
    while (GetTickCount64()<until) value=(value*6364136223846793005ULL)+1442695040888963407ULL;
    return value;
}

__declspec(noinline) std::uint64_t fixture_hot_chain(unsigned depth,std::uint64_t until) {
    volatile std::uint64_t frame[24]{};
    frame[0]=depth+1;
    if (depth) frame[1]=fixture_hot_chain(depth-1,until);
    else frame[1]=fixture_hot_leaf(until);
    for (unsigned i=2;i<24;++i) frame[i]=frame[i-1]^(frame[i-2]+i);
    return frame[23];
}

int fixture_child(std::wstring_view mode) {
    if (mode==L"fixture-hang") {
        for (;;) {volatile auto value=fixture_hot_chain(4,GetTickCount64()+50);(void)value;}
    }
    std::array<char,128> input{};
    DWORD got=0;
    const HANDLE stdin_handle=GetStdHandle(STD_INPUT_HANDLE);
    if (!ReadFile(stdin_handle,input.data(),static_cast<DWORD>(input.size()),&got,nullptr)) return 91;
    if (mode==L"fixture-hot" || mode==L"fixture-disabled") {
        const auto until=GetTickCount64()+300;
        volatile auto value=fixture_hot_chain(14,until);
        (void)value;
    }
    std::string output="FIXTURE-OUT:";
    output.append(input.data(),got);
    DWORD written=0;
    const HANDLE stdout_handle=GetStdHandle(STD_OUTPUT_HANDLE);
    if (!WriteFile(stdout_handle,output.data(),static_cast<DWORD>(output.size()),&written,nullptr) || written!=output.size()) return 92;
    constexpr char error[]="FIXTURE-ERR\n";
    const HANDLE stderr_handle=GetStdHandle(STD_ERROR_HANDLE);
    if (!WriteFile(stderr_handle,error,sizeof(error)-1,&written,nullptr) || written!=sizeof(error)-1) return 93;
    return mode==L"fixture-fail"?7:0;
}

struct StandardCapture {
    std::array<HANDLE,3> old{};
    std::array<Handle,3> files;
    std::filesystem::path directory;
    StandardCapture(const std::filesystem::path& root,std::string_view stem) :directory(root) {
        const std::array<std::wstring,3> names{L"stdin-"+utf8_to_wide(stem)+L".bin",
            L"stdout-"+utf8_to_wide(stem)+L".bin",L"stderr-"+utf8_to_wide(stem)+L".bin"};
        for (std::size_t i=0;i<old.size();++i) old[i]=GetStdHandle(std::array<DWORD,3>{STD_INPUT_HANDLE,STD_OUTPUT_HANDLE,STD_ERROR_HANDLE}[i]);
        Handle input(CreateFileW((directory/names[0]).c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr));
        if (!input) throw Failure("controls stdin capture create failed");
        constexpr char seed[]="controlled-input\n";
        DWORD count=0;
        if (!WriteFile(input.get(),seed,sizeof(seed)-1,&count,nullptr) || count!=sizeof(seed)-1) throw Failure("controls stdin seed write failed");
        SetFilePointer(input.get(),0,nullptr,FILE_BEGIN);
        files[0]=std::move(input);
        for (std::size_t i=1;i<3;++i) {
            files[i].reset(CreateFileW((directory/names[i]).c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,
                CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr));
            if (!files[i]) throw Failure("controls output capture create failed");
        }
        for (std::size_t i=0;i<files.size();++i) {
            const DWORD kind=std::array<DWORD,3>{STD_INPUT_HANDLE,STD_OUTPUT_HANDLE,STD_ERROR_HANDLE}[i];
            if (!SetStdHandle(kind,files[i].get())) throw Failure("controls SetStdHandle failed");
        }
    }
    StandardCapture(const StandardCapture&)=delete;
    StandardCapture& operator=(const StandardCapture&)=delete;
    ~StandardCapture() {
        SetStdHandle(STD_INPUT_HANDLE,old[0]);SetStdHandle(STD_OUTPUT_HANDLE,old[1]);SetStdHandle(STD_ERROR_HANDLE,old[2]);
    }
    std::string read(std::size_t index) {
        SetFilePointer(files[index].get(),0,nullptr,FILE_BEGIN);
        std::string result;
        std::array<char,256> buffer{};
        for (;;) {
            DWORD count=0;
            if (!ReadFile(files[index].get(),buffer.data(),static_cast<DWORD>(buffer.size()),&count,nullptr))
                throw Failure("controls capture ReadFile failed");
            result.append(buffer.data(),count);
            if (count<buffer.size()) break;
        }
        return result;
    }
};

void parser_controls(const std::filesystem::path& root,const std::wstring& executable) {
    const auto scratch=root/L"fixture-parser";
    std::filesystem::create_directories(scratch);
    const auto symbols=root/L"symbols-empty";
    std::filesystem::create_directories(symbols);
    const auto report=root/L"parser-report.json";
    std::array<std::wstring,9> args{L"sampler",L"--child",executable,L"--scratch",scratch.wstring(),
        L"--report",report.wstring(),L"--symbols",symbols.wstring()};
    std::array<wchar_t*,9> pointers{};
    for (std::size_t i=0;i<args.size();++i) pointers[i]=args[i].data();
    const auto parsed=parse_options(static_cast<int>(pointers.size()),pointers.data());
    validate_options(parsed);
    control_require(parsed.interval_ms==default_interval_ms && !parsed.disabled,"default sampler options differ");
    args[0]=L"sampler";
    std::array<std::wstring,11> bad{L"sampler",L"--child",executable,L"--scratch",scratch.wstring(),
        L"--report",report.wstring(),L"--symbols",symbols.wstring(),L"--interval-ms",L"0"};
    std::array<wchar_t*,11> bad_pointers{};
    for (std::size_t i=0;i<bad.size();++i) bad_pointers[i]=bad[i].data();
    bool rejected=false;
    try {(void)parse_options(static_cast<int>(bad_pointers.size()),bad_pointers.data());}
    catch (const Failure&) {rejected=true;}
    control_require(rejected,"invalid sampling interval was admitted");
}

void callback_controls() {
    std::array<unsigned char,max_target_read> stack{};
    stack.fill(0x5a);
    std::array<unsigned char,max_target_read> output{};
    WalkContext context{0x100000,stack.data(),stack.size(),nullptr};
    active_walk=&context;
    DWORD copied=0;
    const BOOL first=snapshot_read_memory(nullptr,context.stack_base,output.data(),
        static_cast<DWORD>(output.size()),&copied);
    control_require(first && copied==max_callback_read && context.callback_calls==1 &&
        context.callback_bytes==max_callback_read && output.front()==0x5a && output.back()==0x5a,
        "exact callback byte cap did not serve the captured stack");
    copied=99;
    const BOOL over=snapshot_read_memory(nullptr,context.stack_base,output.data(),1,&copied);
    control_require(!over && copied==0 && context.callback_calls==2 && context.budget_denials==1 &&
        context.callback_failures==1,"callback byte budget denial was not recorded");

    WalkContext calls{};
    active_walk=&calls;
    std::array<unsigned char,1> byte{};
    for (std::size_t i=0;i<max_callback_calls;++i) {
        copied=99;
        control_require(!snapshot_read_memory(nullptr,0x800000,byte.data(),1,&copied) && copied==0,
            "unmapped callback test unexpectedly read memory");
    }
    copied=99;
    control_require(!snapshot_read_memory(nullptr,0x800000,byte.data(),1,&copied) && copied==0 &&
        calls.callback_calls==max_callback_calls && calls.unmapped_reads==max_callback_calls &&
        calls.budget_denials==1,
        "callback call cap did not include failed and unmapped requests");
    active_walk=nullptr;
}

void image_controls(const std::filesystem::path& root,const std::wstring& executable) {
    std::array<unsigned char,512> fake_image{};
    Module fake;
    fake.base=0x10000000;fake.size=static_cast<std::uint32_t>(fake_image.size());
    fake.image=fake_image.data();fake.image_valid=true;
    fake.readonly_ranges[0]={100,200};fake.readonly_count=1;
    fake.blocked={{130,140},{160,168}};
    control_require(admitted_image_span(fake,100,16) && admitted_image_span(fake,150,8) &&
        !admitted_image_span(fake,129,2) && !admitted_image_span(fake,130,1) &&
        !admitted_image_span(fake,160,8) && !admitted_image_span(fake,199,2),
        "module callback admitted IAT/relocation or out-of-span bytes");

    Module capped;
    capped.path=(root/L"must-not-open.exe").wstring();
    capped.size=static_cast<std::uint32_t>(max_image_bytes+1);
    std::uint64_t total=0;
    map_readonly_image(capped,total);
    control_require(capped.identity_error=="module_image_capacity" && !capped.file && !capped.image && !total,
        "oversized local image opened or mapped before capacity rejection");

    const auto copied_path=root/L"malformed-pdata-copy.exe";
    std::filesystem::copy_file(executable,copied_path);
    std::ifstream input(copied_path,std::ios::binary|std::ios::ate);
    if (!input) throw Failure("cannot read test-owned malformed image copy");
    const auto file_size=input.tellg();
    control_require(file_size>0 && file_size<=static_cast<std::streamoff>(max_image_bytes),
        "test image exceeds its local parser cap");
    std::vector<unsigned char> bytes(static_cast<std::size_t>(file_size));
    input.seekg(0);
    input.read(reinterpret_cast<char*>(bytes.data()),static_cast<std::streamsize>(bytes.size()));
    control_require(bool(input),"short read of test-owned image copy");
    input.close();
    auto* dos=reinterpret_cast<IMAGE_DOS_HEADER*>(bytes.data());
    control_require(dos->e_magic==IMAGE_DOS_SIGNATURE && dos->e_lfanew>0 &&
        static_cast<std::size_t>(dos->e_lfanew)+sizeof(IMAGE_NT_HEADERS64)<=bytes.size(),
        "controls executable has unsupported PE headers");
    auto* nt=reinterpret_cast<IMAGE_NT_HEADERS64*>(bytes.data()+dos->e_lfanew);
    auto& exception=nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXCEPTION];
    control_require(nt->Signature==IMAGE_NT_SIGNATURE && exception.Size && exception.Size%sizeof(IMAGE_RUNTIME_FUNCTION_ENTRY)==0 &&
        exception.Size<std::numeric_limits<DWORD>::max(),"controls executable has unsupported pdata directory");
    ++exception.Size;
    std::ofstream output_file(copied_path,std::ios::binary|std::ios::trunc);
    output_file.write(reinterpret_cast<const char*>(bytes.data()),static_cast<std::streamsize>(bytes.size()));
    output_file.close();
    control_require(bool(output_file),"could not write malformed pdata copy");
    Module malformed;
    malformed.path=copied_path.wstring();malformed.size=nt->OptionalHeader.SizeOfImage;
    total=0;
    map_readonly_image(malformed,total);
    control_require(malformed.identity_error=="invalid_exception_directory" && !malformed.exception_rva,
        "malformed pdata copy was accepted");
    // This mapped copy is only parser input and is never executed.
}

Options fixture_options(const std::filesystem::path& root,const std::wstring& executable,
                        std::wstring_view mode,std::string_view report_name,bool disabled=false);

void serializer_overflow_controls(const std::filesystem::path& root,const std::wstring& executable) {
    auto options=fixture_options(root,executable,L"fixture-parser","overflow-unused.json");
    RunReport report;
    report.status="failed";
    report.error.assign(max_report_bytes,'x');
    report.samples.resize(2);
    report.modules.resize(1);
    int result=0;
    const auto json=serialize_report(options,report,result);
    control_require(result==2 && report.report_truncated && report.error=="report_serialization_failed" &&
        report.omitted_sample_records==2 && report.omitted_module_records==1 && json.size()<=max_report_bytes &&
        json.find("\"report_truncated\":true")!=std::string::npos &&
        json.find("\"omitted_sample_records\":2")!=std::string::npos &&
        json.find("\"omitted_module_records\":1")!=std::string::npos,
        "oversized test report did not retain bounded truncation evidence");
}

Options fixture_options(const std::filesystem::path& root,const std::wstring& executable,
                        std::wstring_view mode,std::string_view report_name,bool disabled) {
    const auto scratch=root/std::filesystem::path(mode);
    const auto symbols=root/L"symbols-empty";
    std::filesystem::create_directories(scratch);
    std::filesystem::create_directories(symbols);
    Options options{executable,scratch.wstring(),(root/std::filesystem::path(utf8_to_wide(report_name))).wstring(),symbols.wstring(),2,disabled};
    validate_options(options);
    return options;
}

struct FixtureResult {std::string json;int exit_code=0;RunReport report;};

FixtureResult run_fixture(const Options& options,std::string_view capture_name) {
    StandardCapture capture(std::filesystem::path(options.report).parent_path(),capture_name);
    validate_options(options);
    FixtureResult result;
    result.exit_code=run_child(options,result.report);
    write_new_report(options.report,build_report(options,result.report));
    const auto output=capture.read(1),error=capture.read(2);
    control_require(output=="FIXTURE-OUT:controlled-input\n","child stdout was not forwarded byte-for-byte");
    control_require(error=="FIXTURE-ERR\n","child stderr was not forwarded byte-for-byte");
    std::ifstream report(options.report,std::ios::binary);
    if (!report) throw Failure("controls could not read sampler report");
    result.json={std::istreambuf_iterator<char>(report),std::istreambuf_iterator<char>()};
    return result;
}

void cleanup_controls(const std::filesystem::path& root,const std::wstring& executable) {
    auto options=fixture_options(root,executable,L"fixture-hang","cleanup-unused-report.json");
    RunReport report;
    Handle retained_process;
    {
        Child child=launch_child(options,report);
        if (!DuplicateHandle(GetCurrentProcess(),child.process.get(),GetCurrentProcess(),
            &retained_process.value,0,FALSE,DUPLICATE_SAME_ACCESS))
            throw Failure("controls could not retain child process handle");
        const DWORD resumed=ResumeThread(child.thread.get());
        control_require(resumed==1,"cleanup fixture did not resume exactly once");
    }
    control_require(WaitForSingleObject(retained_process.get(),5000)==WAIT_OBJECT_0,
        "owned child survived job close/cleanup");
    DWORD exit=STILL_ACTIVE;
    control_require(GetExitCodeProcess(retained_process.get(),&exit) && exit!=STILL_ACTIVE,
        "cleaned child exit was not observed");
}

void assignment_failure_controls(const std::filesystem::path& root,const std::wstring& executable) {
    auto options=fixture_options(root,executable,L"fixture-hang","assignment-failure-unused.json");
    options.report=(root/L"assignment-failure-report.json").wstring();
    StandardCapture capture(root,"assignment-failure");
    const int result=execute(options,true);
    control_require(result!=0,"forced job-assignment failure returned success");
    control_require(capture.read(1).empty() && capture.read(2).empty(),
        "suspended child emitted data before failed assignment");
    std::ifstream input(options.report,std::ios::binary);
    if (!input) throw Failure("assignment failure report was not preserved");
    const std::string json{std::istreambuf_iterator<char>(input),std::istreambuf_iterator<char>()};
    control_require(json.find("\"child_launched\":true")!=std::string::npos &&
        json.find("\"job_assigned\":false")!=std::string::npos &&
        json.find("\"job_assignment_error\":5")!=std::string::npos &&
        json.find("\"termination_attempted\":true")!=std::string::npos &&
        json.find("\"termination_succeeded\":true")!=std::string::npos &&
        json.find("\"cleanup_exit_observed\":true")!=std::string::npos &&
        json.find("\"cleanup_exit_code\":126")!=std::string::npos,
        "forced assignment failure report omitted owned-child termination evidence");
}

void pause_watchdog_controls(const std::filesystem::path& root,const std::wstring& executable) {
    const auto options=fixture_options(root,executable,L"fixture-hang","pause-watchdog-unused.json");
    RunReport watched_report,sentinel_report;
    Child watched=launch_child(options,watched_report);
    Child sentinel=launch_child(options,sentinel_report);
    control_require(ResumeThread(sentinel.thread.get())==1,"sentinel child did not resume exactly once");
    Watchdog watchdog(watched.job.get(),&watched_report);
    control_require(ResumeThread(watched.thread.get())==1,"watched child did not resume exactly once");
    control_require(SuspendThread(watched.thread.get())==0,"watched child did not accept a single test suspension");
    std::int64_t began=0;
    control_require(counter(began),"pause watchdog control clock unavailable");
    watchdog.pause_started(began);
    const DWORD stopped=WaitForSingleObject(watched.process.get(),2000);
    std::int64_t ended=0;
    const bool ended_counter=counter(ended);
    if (stopped!=WAIT_OBJECT_0) {
        const DWORD remaining=WaitForSingleObject(watched.process.get(),0);
        if (remaining!=WAIT_OBJECT_0) (void)ResumeThread(watched.thread.get());
        watchdog.pause_ended();
        TerminateJobObject(watched.job.get(),127);
    }
    watchdog.stop();
    const auto pause_elapsed=ended_counter?elapsed_ns(began,ended,watchdog.frequency()):0;
    control_require(stopped==WAIT_OBJECT_0 && ended_counter && pause_elapsed>=250000000 &&
        pause_elapsed<2000000000 && watchdog.reason()==2 && watched_report.watchdog_reason==2,
        "suspended-pause watchdog did not terminate its owned child");
    DWORD exit=STILL_ACTIVE;
    control_require(GetExitCodeProcess(watched.process.get(),&exit) && exit==125,
        "pause watchdog child exit code differs");
    control_require(WaitForSingleObject(sentinel.process.get(),0)==WAIT_TIMEOUT,
        "pause watchdog terminated a child outside its job");
    TerminateJobObject(sentinel.job.get(),127);
    control_require(WaitForSingleObject(sentinel.process.get(),2000)==WAIT_OBJECT_0,
        "sentinel child cleanup failed");
}

std::filesystem::path control_root() {
    std::array<wchar_t,32768> configured{};
    const DWORD length=GetEnvironmentVariableW(L"OPENPOKER_NATIVE_OWNED_CHILD_SAMPLE_CONTROL_DIR",
        configured.data(),static_cast<DWORD>(configured.size()));
    std::filesystem::path root;
    if (length) {
        if (length>=configured.size()) throw Failure("control output path exceeds its cap");
        root=configured.data();
        if (!root.is_absolute() || root.native().size()>512 || std::filesystem::exists(root))
            throw Failure("configured control output must be absolute, bounded, and new");
        root=std::filesystem::weakly_canonical(root.parent_path())/root.filename();
    } else {
        root=std::filesystem::weakly_canonical(std::filesystem::temp_directory_path())/
            (L"owned-child-stack-controls-"+std::to_wstring(GetCurrentProcessId()));
        if (root.native().size()>512 || std::filesystem::exists(root))
            throw Failure("fallback control output is not new or exceeds its path cap");
    }
    std::filesystem::create_directory(root);
    return root;
}

} // namespace

int wmain(int argc,wchar_t** argv) {
    using namespace owned_child_stack_sample;
    if (argc==2) {
        const std::wstring mode=std::filesystem::path(argv[1]).filename().wstring();
        if (mode==L"fixture-hot" || mode==L"fixture-disabled" || mode==L"fixture-fail" || mode==L"fixture-hang")
            return fixture_child(mode);
    }
    try {
        if (argc!=1) throw Failure("controls take no command-line arguments");
        const auto executable=current_executable();
        const auto root=control_root();
        parser_controls(root,executable);
        callback_controls();
        image_controls(root,executable);
        serializer_overflow_controls(root,executable);
        const auto enabled_options=fixture_options(root,executable,L"fixture-hot", "enabled-report.json");
        const auto enabled=run_fixture(enabled_options,"enabled");
        control_require(enabled.exit_code==0,"enabled hot child failed");
        control_require(enabled.json.find("\"status\":\"completed_partial_unwinds\"")!=std::string::npos,
                "enabled child did not complete with a sampling report");
        control_require(!enabled.report.samples.empty(),"enabled hot child produced no samples");
        bool advanced=false;
        for (const auto& sample:enabled.report.samples) {
            control_require(sample.rip!=0 && sample.target_read_bytes<=max_target_read &&
                sample.callback_bytes<=max_callback_read && sample.frame_count<=max_frames,
                "sample seed or read/frame cap differs");
            for (std::size_t i=0;i<sample.frame_count;++i) {
                control_require(!(sample.frames[i].pc==sample.rip && sample.frames[i].sp==sample.rsp),
                    "seed context was counted as an advanced unwind frame");
                if (sample.frame_count>=2 && sample.frames[i].sp>sample.rsp) advanced=true;
            }
        }
        control_require(advanced,"deep noinline hot fixture produced no advancing unwind frame");
        control_require(enabled.json.find("\"seed_rip\":\"0x")!=std::string::npos,
            "enabled report omitted raw seed RIP");

        const auto disabled=fixture_options(root,executable,L"fixture-disabled","disabled-report.json",true);
        const auto disabled_run=run_fixture(disabled,"disabled");
        control_require(disabled_run.exit_code==0 && disabled_run.json.find("\"status\":\"completed_disabled\"")!=std::string::npos,
                "disabled wrapper baseline failed");
        control_require(disabled_run.json.find("\"samples\":[]")!=std::string::npos,
                "disabled mode unexpectedly sampled");

        const auto failed=fixture_options(root,executable,L"fixture-fail","failed-report.json");
        const auto failed_run=run_fixture(failed,"failed");
        control_require(failed_run.exit_code==4 && failed_run.json.find("\"status\":\"child_failed\"")!=std::string::npos &&
                failed_run.json.find("\"child_exit_code\":7")!=std::string::npos,
                "nonzero child exit was not retained as a failed run");

        cleanup_controls(root,executable);
        assignment_failure_controls(root,executable);
        pause_watchdog_controls(root,executable);
        std::puts("OWNED_CHILD_STACK_SAMPLE_CONTROLS PASS");
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr,"owned child sampler controls failed: %s\n",error.what());
        return 1;
    }
}

#else
int main() {
    std::fputs("owned child sampler controls require Windows x64\n",stderr);
    return 2;
}
#endif
