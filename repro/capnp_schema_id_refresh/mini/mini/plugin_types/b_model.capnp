@0xa32ab4a8c784ba9d;

using Anot = import "rpp_common/anot.capnp";
using A = import "mini/a_model.capnp";

interface BModel $Anot.plugin("BModel") {
    graph @0 () -> (payload :A.Payload);
}
