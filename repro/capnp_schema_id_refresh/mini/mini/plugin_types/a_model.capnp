@0x932ab4a8c784ba9c;

using Anot = import "rpp_common/anot.capnp";

struct Payload {
    values @0 :List(Float64);
}

interface AModel $Anot.plugin("AModel") {
    graph @0 () -> (payload :Payload);
}
