import re





def to_pascal_case(value: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", value)
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def first_char_to_upper(value: str) -> str:
    if not value:
        return value
    return value[0].upper() + value[1:]


adapt_capnp_field_name = first_char_to_upper