// Standalone repro for slow browser-wasm AOT (aot-instances.dll pass) caused by polymorphic recursion over struct
// type arguments. Mirrors the shape of ILGPU's ArgumentMapper (MapInstance -> MapStructInstance -> MapInstance with
// StructureSource<TSource> / StructureTarget<TTarget>), with no dependency on ILGPU.
//
// ON  (default):                     MapInstance<TEmitter, TSource, TTarget> recurses with the source/target wrapped
//                                     in one more generic struct level per struct field depth. At run time the depth
//                                     is bounded by the real struct nesting (2 here); mono AOT cannot know that and
//                                     instantiates to its generic depth cap.
// OFF (-p:NoPolymorphicRecursion=true): the same walk with a non-generic field path, a fixed instantiation set.
using System;
using System.Collections.Generic;
using System.Reflection;

public interface IEmitter { void Emit(string op); }
public struct ListEmitter : IEmitter { public List<string> Ops; public void Emit(string op) => Ops.Add(op); }
public struct CountEmitter : IEmitter { public int Count; public void Emit(string op) => Count++; }

public interface ISource { Type SourceType { get; } string Describe(); }
public interface ITarget { Type TargetType { get; } string Describe(); }

public readonly struct ArgumentSource : ISource
{
    public ArgumentSource(Type type, int index) { SourceType = type; Index = index; }
    public Type SourceType { get; }
    public int Index { get; }
    public string Describe() => "arg" + Index;
}

public readonly struct LocalTarget : ITarget
{
    public LocalTarget(Type type, int local) { TargetType = type; Local = local; }
    public Type TargetType { get; }
    public int Local { get; }
    public string Describe() => "loc" + Local;
}

#if !NOREC
public readonly struct StructureSource<TParent> : ISource where TParent : struct, ISource
{
    public StructureSource(in TParent parent, FieldInfo field) { Parent = parent; Field = field; }
    public TParent Parent { get; }
    public FieldInfo Field { get; }
    public Type SourceType => Field.FieldType;
    public string Describe() => Parent.Describe() + "." + Field.Name;
}

public readonly struct StructureTarget<TParent> : ITarget where TParent : struct, ITarget
{
    public StructureTarget(in TParent parent, FieldInfo field) { Parent = parent; Field = field; }
    public TParent Parent { get; }
    public FieldInfo Field { get; }
    public Type TargetType => Field.FieldType;
    public string Describe() => Parent.Describe() + "." + Field.Name;
}
#else
public readonly struct PathSource<TRoot> : ISource where TRoot : struct, ISource
{
    public PathSource(in TRoot root, FieldInfo[] path) { Root = root; Path = path; }
    public TRoot Root { get; }
    public FieldInfo[] Path { get; }
    public Type SourceType => Path.Length == 0 ? Root.SourceType : Path[^1].FieldType;
    public string Describe() { var s = Root.Describe(); foreach (var f in Path) s += "." + f.Name; return s; }
    public PathSource<TRoot> Append(FieldInfo f) { var p = new FieldInfo[Path.Length + 1]; Path.CopyTo(p, 0); p[^1] = f; return new(Root, p); }
}

public readonly struct PathTarget<TRoot> : ITarget where TRoot : struct, ITarget
{
    public PathTarget(in TRoot root, FieldInfo[] path) { Root = root; Path = path; }
    public TRoot Root { get; }
    public FieldInfo[] Path { get; }
    public Type TargetType => Path.Length == 0 ? Root.TargetType : Path[^1].FieldType;
    public string Describe() { var s = Root.Describe(); foreach (var f in Path) s += "." + f.Name; return s; }
    public PathTarget<TRoot> Append(FieldInfo f) { var p = new FieldInfo[Path.Length + 1]; Path.CopyTo(p, 0); p[^1] = f; return new(Root, p); }
}
#endif

public static class Mapper
{
#if !NOREC
    public static void MapInstance<TEmitter, TSource, TTarget>(ref TEmitter emitter, in TSource source, in TTarget target)
        where TEmitter : struct, IEmitter where TSource : struct, ISource where TTarget : struct, ITarget
    {
        if (source.SourceType.IsPrimitive || source.SourceType.IsEnum)
            emitter.Emit($"store {target.Describe()} <- {source.Describe()}");
        else
            MapStructInstance(ref emitter, source, target);
    }

    static void MapStructInstance<TEmitter, TSource, TTarget>(ref TEmitter emitter, in TSource source, in TTarget target)
        where TEmitter : struct, IEmitter where TSource : struct, ISource where TTarget : struct, ITarget
    {
        var sf = source.SourceType.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        var tf = target.TargetType.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        for (int i = 0; i < sf.Length; i++)
            MapInstance(ref emitter, new StructureSource<TSource>(source, sf[i]), new StructureTarget<TTarget>(target, tf[i]));
    }

    public static void Map<TEmitter, TSource, TTarget>(ref TEmitter emitter, in TSource source, in TTarget target)
        where TEmitter : struct, IEmitter where TSource : struct, ISource where TTarget : struct, ITarget
        => MapInstance(ref emitter, source, target);
#else
    static void MapPath<TEmitter, TRootS, TRootT>(ref TEmitter emitter, in PathSource<TRootS> source, in PathTarget<TRootT> target)
        where TEmitter : struct, IEmitter where TRootS : struct, ISource where TRootT : struct, ITarget
    {
        if (source.SourceType.IsPrimitive || source.SourceType.IsEnum)
        {
            emitter.Emit($"store {target.Describe()} <- {source.Describe()}");
            return;
        }
        var sf = source.SourceType.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        var tf = target.TargetType.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        for (int i = 0; i < sf.Length; i++)
            MapPath(ref emitter, source.Append(sf[i]), target.Append(tf[i]));
    }

    public static void Map<TEmitter, TSource, TTarget>(ref TEmitter emitter, in TSource source, in TTarget target)
        where TEmitter : struct, IEmitter where TSource : struct, ISource where TTarget : struct, ITarget
        => MapPath(ref emitter, new PathSource<TSource>(source, Array.Empty<FieldInfo>()), new PathTarget<TTarget>(target, Array.Empty<FieldInfo>()));
#endif
}

public struct Inner { public int A; public float B; }
public struct Outer { public Inner I; public long C; }

public static class Program
{
    public static int Main(string[] args)
    {
        var src = new ArgumentSource(typeof(Outer), 0);
        var dst = new LocalTarget(typeof(Outer), 1);
        var list = new ListEmitter { Ops = new List<string>() };
        Mapper.Map(ref list, src, dst);
        var count = new CountEmitter();
        Mapper.Map(ref count, src, dst);
        foreach (var op in list.Ops) Console.WriteLine(op);
        Console.WriteLine($"ops {list.Ops.Count} / {count.Count}");
        return list.Ops.Count == 3 && count.Count == 3 ? 0 : 1;
    }
}
