# Mono browser-wasm AOT: polymorphic recursion over struct type arguments makes the aot-instances pass take hours

Reported upstream: [dotnet/runtime#137919](https://github.com/dotnet/runtime/issues/137919).

A browser-wasm AOT publish (`RunAOTCompilation=true`, default `WasmDedup=true`) of a tiny console app spends most of
its time in one single-threaded `mono-aot-cross` pass, `aot-instances.dll`. It happens when a generic method recurses
into itself with its struct type arguments wrapped one level deeper:

```csharp
void MapInstance<TSource, TTarget>(in TSource s, in TTarget t)        // TSource, TTarget : struct
    => MapInstance(new StructureSource<TSource>(s, f), new StructureTarget<TTarget>(t, f));
```

At run time the depth is bounded by real data (here 2). Mono AOT cannot know that, so it instantiates the chain up to its
generic depth cap. Each level needs gsharedvt wrappers, and building their signatures
(`mini_get_underlying_signature` -> `get_wrapper_shared_type_full` <-> `get_wrapper_shared_vtype`) re-expands the whole
nested struct at every call, with no memoization.

The same app with a non-generic field path (`-p:NoPolymorphicRecursion=true`) publishes in under a minute.

* **Live results** (measured by this repo's GitHub Actions on .NET 9, 10 and 11, both arms) and the built apps:
  see the GitHub Pages site of this repository.
* **Source:** [`src/Program.cs`](src/Program.cs). The ON and OFF arms differ only in the `#if NOREC` blocks.

## Reproduce

```
dotnet workload install wasm-tools
dotnet publish src/Repro.csproj -c Release                                   # ON
dotnet publish src/Repro.csproj -c Release -p:NoPolymorphicRecursion=true    # OFF
```

Add `-p:ReproTfm=net9.0` / `net11.0` with the matching SDK (a global `-p:TargetFramework` does not reach the
WebAssembly SDK's nested publish). `tools/extract.py` reads mono's own `Compiled` and
`JIT time` lines out of a replayed binlog (`dotnet msbuild pub.binlog -noconlog -flp:logfile=diag.log;verbosity=diagnostic`).

## Where the time goes

Profiled with a user-mode stack sampler and the public symbols for `mono-aot-cross.exe` 10.0.14 (Windows, 100 ms
samples), on the real-world case this was found in (an app using ILGPU, whose `ArgumentMapper` has this shape).
In every 10-minute window of an 84-minute `aot-instances` pass, 94-100% of samples were under:

```
compile_method
  add_gsharedvt_wrappers
    mini_get_gsharedvt_in_sig_wrapper
      mini_get_underlying_signature
        get_wrapper_shared_type_full <-> get_wrapper_shared_vtype     (12-17 levels deep per sample, max 22)
          mono_class_inflate_generic_class_checked                     (68% inclusive)
            mono_metadata_inflate_generic_inst / type_dup / malloc / free
```

Mono's own counters for that pass: 54,728 instances in 1,049 s of JIT (19.2 ms each) in the emit phase, against
0.54 ms per method in the 105 ordinary per-assembly passes of the same app. The collect phase, which prints no timing,
took most of the rest.

## Am I affected? Workaround

Signs, on a browser-wasm AOT publish with the default `WasmDedup=true`:

* almost all `mono-aot-cross` passes finish in a minute or two, then `[n/n] aot-instances.dll -> aot-instances.dll.bc`
  arrives tens of minutes or hours later, on one core;
* a profile of that `mono-aot-cross` process sits in `add_gsharedvt_wrappers` -> `get_wrapper_shared_type_full` /
  `get_wrapper_shared_vtype` (Microsoft's public symbol server has the PDB for the Windows `mono-aot-cross.exe`);
* in `aot-instances.dll.bc`, instance names repeat one generic struct many times in a row (`Wrapper_1_Wrapper_1_...`).

Workaround: find the generic method that calls itself with its struct type argument wrapped one level deeper, and
make that recursion non-generic. The OFF arm here keeps the root type generic but carries the field path as a plain
array (`PathSource<TRoot>`), so the instantiation set is fixed. That is how ILGPU fixed its `ArgumentMapper`
(SpawnDev.ILGPU 5.4.38): a real app's 89-minute `aot-instances` pass dropped to about a minute.

`-p:WasmDedup=false` is not a measured workaround for this: the cost moves out of the single dedup pass, but whether the
per-assembly passes then pay it was not tested here, and it makes `dotnet.native.wasm` much larger.

## Related upstream work

dotnet/runtime #135029 / #135438 ("Fix stack overflow normalizing self-referencing struct wrappers") add a parent-frame
chain with cycle detection and a depth limit of 16 to `get_wrapper_shared_vtype`. They target a stack overflow. The
change is in main (.NET 12) and was backported to release/11.0 on 2026-11-16 (#135334), after the 11.0.0 release, so
every row on the results page runs without it. Whether that depth limit also bounds this cost is **untested**:
no public build has it yet (the daily .NET 11 SDKs, 11.0.200-preview.26567.117 on 2026-11-19, still bundle runtime
11.0.0-rc.2.26508.107), and .NET 12 dailies run browser-wasm on CoreCLR, without Mono AOT.
