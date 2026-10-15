// O08: static cache whose accesses are strictly confined within compute().
// Legacy analysis treats all static fields as GLOBAL -> HEAP.
// Under Scope LCA, compute() is the Lowest Common Ancestor of all accessors of cache,
// so cache and its objects are captured by compute()'s frame.
public class O08 {
    static Cache cache;

    public static void main(String[] args) {
        compute(10);
        compute(20);
    }

    static int compute(int limit) {
        cache = new Cache();              // A: allocated inside compute, stored to static
        cache.data = new Item();          // B: allocated inside compute, stored into A
        int s = 0;
        for (int i = 0; i < limit; i++) {
            s += cache.data.n;
        }
        cache = null;                     // dead at exit of compute
        return s;
    }
}

class Cache { Item data; }
class Item { int n = 42; }
