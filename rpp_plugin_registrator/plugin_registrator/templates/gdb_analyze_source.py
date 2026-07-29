GDB_ANALYZE_SOURCE_TEMPLATE = """

file {dummy_file_path}
python
import gdb, re, json

# 1. Start the program and set a breakpoint at main
gdb.execute("tbreak main")
gdb.execute("run")

so_path = "{so_path}"

def read_string(value):
    return value["_M_dataplus"]["_M_p"].string()

def iterate_vector(vec):

    start = vec["_M_impl"]["_M_start"]
    finish = vec["_M_impl"]["_M_finish"]

    while start != finish:
        yield start.dereference()
        start += 1

def iterate_map(mp):

    header = (
        mp["_M_t"]
        ["_M_impl"]
        ["_M_header"]
    )

    printer = gdb.default_visualizer(mp)
    if printer is None:
        raise RuntimeError("No std::map pretty printer available")

    children = list(printer.children())
    for i in range(0, len(children), 2):
        key_value = children[i][1]    # gdb.Value za ključ (std::string)
        val_value = children[i+1][1]  # gdb.Value za vrijednost (ParameterValue)

        # Čitamo string ključa i vraćamo ga zajedno s vrijednošću
        yield read_string(key_value), val_value


def variant_active_value(variant, variant_text, variant_type):

    printer = gdb.default_visualizer(variant)

    if printer is None:
        raise RuntimeError(
            "No std::variant pretty printer"
        )
    m = re.search(r'index\\s*(\\d+)', variant_text)
    if not m:
        raise RuntimeError("Could not determine variant index")
    idx = int(m.group(1))

    active_type = variant.type.template_argument(idx)


    if variant_type == "primitive":
        return variant.cast(active_type)

    pure_type = active_type.unqualified()
    return variant.address.cast(pure_type.pointer()).dereference()


def normalize_type(t):

    if "basic_string" in t:
        return "string"

    if t in ("long", "long int", "int64_t"):
        return "int"
    if t in ("float", "float32", "float64", "double"):
        return "float"
    if t == "bool":
        return "bool"
    if t == "void":
        return "void"
    if t in ("object", "Object") \\
        or "std::map" in t \\
        or "std::unordered_map" in t:
        return "object"
    if t in ("array", "Array", "list") \\
        or "std::vector" in t \\
        or "std::list" in t:
        return "array"
    return t


# ============================================================
# primitive conversion
# ============================================================

def convert_primitive(value):

    t = str(value.type)
    t = normalize_type(t)

    if t == "bool":
        return bool(value)
    if t == "int":
        return int(value)
    if t == "float":
        return float(value)
    if t == "string":
        return read_string(value)
    if t == "void":
        return None
    raise RuntimeError(f"Unknown primitive type: {{t}}")

# ============================================================
# ParameterValue parser
# ============================================================

def parse_parameter_value(name, parameter_value):

    variant = parameter_value["value"]

    printer = gdb.default_visualizer(variant)

    if printer is None:
        raise RuntimeError(
            "No variant printer"
        )


    variant_text = printer.to_string()

    # --------------------------------------------------------
    # Primitive
    # --------------------------------------------------------

    if (
        "std::vector" not in variant_text
        and "std::map" not in variant_text
    ):

        value = variant_active_value(variant, variant_text, "primitive")

        return {{
            "name": name,
            "type": normalize_type(
                str(value.type)
            ),
            "default_value": convert_primitive(value)
        }}



    # --------------------------------------------------------
    # Vector
    # --------------------------------------------------------

    if "std::vector" in variant_text:

        # The printer child is the actual vector
        vec = variant_active_value(variant, variant_text, "array")

        elements = []

        for i, element in enumerate(
            iterate_vector(vec)
        ):

            elements.append(
                parse_parameter_value(
                    str(i),
                    element
                )
            )


        return {{
            "name": name,
            "type": "array",
            "element_type": (
                normalize_type(elements[0]["type"])
                if elements
                else None
            ),
            "elements": elements,
        }}



    # --------------------------------------------------------
    # Map/Object
    # --------------------------------------------------------

    if "std::map" in variant_text:

        mp = variant_active_value(variant, variant_text, "object")

        fields = {{}}

        for key, value in iterate_map(mp):


            fields[key] = parse_parameter_value(
                key,
                value
            )


        return {{
            "name": name,
            "type": "object",
            "fields": fields,
        }}


    raise RuntimeError(
        f"Unknown variant type: {{variant_text}}"
    )



def parse_plugin_source(symbol):


    result = {{
        "Parameters": {{}},
        "Components": {{}}
    }}

    try:
        params = gdb.parse_and_eval(
            f"{{symbol}}::PARAMETERS"
        )

        for param in iterate_vector(params):

            name = read_string(
                param["name"]
            )

            result["Parameters"][name] = parse_parameter_value(
                name,
                param["defaultValue"]
            )
    except Exception as e:
        msg = str(e)
        if not "There is no field named PARAMETERS" in msg:
            raise e


    try:
        components = gdb.parse_and_eval(
            f"{{symbol}}::COMPONENTS"
        )

        for key, value in iterate_map(components):
            result["Components"][key] = read_string(value)
    except Exception as e:
        msg = str(e)
        if not "There is no field named COMPONENTS" in msg:
            raise e

    return result


try:
    gdb.execute(f'set $handle = (void*)__libc_dlopen_mode("{so_path}", 1)')
    gdb.execute("sharedlibrary")
    # 3. Configuration of better output formatting (GDB now has vectors and maps in memory!)

    result = parse_plugin_source("{class_name}")


    print("\\nRESULT_START")
    print(json.dumps(result))
    print("\\nRESULT_END")

except Exception as e:
    print(f"\\n[ERROR DURING GDB ANALYSIS]: {{str(e)}}")

# Čistimo i izlazimo
gdb.execute("kill")
gdb.execute("quit")
end
"""