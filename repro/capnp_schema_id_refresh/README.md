# Reproduction for #27: a refresh breaks a library whose schemas import each other

`mini/` is a library with two schemas. `b_model.capnp` imports `a_model.capnp` and uses its `Payload` struct.

## Run

In the CI container of this repository (`rpp` installed, `RPP_CPP_CORE_PATH` set):

```
bash repro/capnp_schema_id_refresh/reproduce.sh
```

or by hand, with a throw-away RPP home:

```
H=$(mktemp -d)/.rpp
rpp --rpp-home $H init-home
rpp --rpp-home $H registry config set RPP_CPP_CORE_PATH $RPP_CPP_CORE_PATH
rpp --rpp-home $H library register repro/capnp_schema_id_refresh/mini   # succeeds
rpp --rpp-home $H library refresh mini                                    # fails
```

## Result on develop

```
capnp_gen/mini/b_model.capnp.c++:126:4: error: 's_<id>' was not declared in this scope
```

## Why

A refresh registers every schema again with `override=True`, and each registration writes a new random schema id (`overwrite_capnp_schema_id`). `a_model.capnp` gets a new id; `b_model.capnp.c++` still refers to the old one and is linked into every compile of the library.
