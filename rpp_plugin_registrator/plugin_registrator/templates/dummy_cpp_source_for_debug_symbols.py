DUMMY_CPP_SOURCE_FOR_DEBUG_SYMBOLS_TEMPLATE = """
#include <iostream>
#include <string>
#include <memory>
#include <vector>
#include <map>
#include <dlfcn.h>

void keep_symbols_alive() {{
    std::vector<std::string> v;
    std::map<std::string, int> m;
    std::unique_ptr<std::string> p = std::make_unique<std::string>("Hello, World!");
    if (v.size() + m.size() + p->size() == 9999) {{
        std::cout << "Fake condition to keep symbols alive" << std::endl;
    }}
}}

int main() {{
    void* handle = dlopen("{plugin_source_file}", RTLD_NOW | RTLD_GLOBAL);
    if (!handle) {{
        std::cerr << "Failed to load plugin: " << dlerror() << std::endl;
        return 1;
    }}
    std::cout << "Plugin successfully mapped into RAM with complete C++ environment!" << std::endl;
    return 0; // Breakpoint will catch the process here
}}
"""