import java.lang.management.ManagementFactory;
import com.sun.management.HotSpotDiagnosticMXBean;

// D01: a known heap for checking the snapshot ownership tree (hprof_tree.py). It dumps its own
// heap from inside use(), two frames deep, and then uses every object again so that none of
// them is dead at the dump. Expected tree: 02-Current-Work/01-Design/2026-09-24-Ownership-Trees.md
// §6.2, and the table in tools/ownership/dyn/README.md.
public class D01 {
    static Box kept;                            // G: owned by GLOBAL

    public static void main(String[] args) throws Exception {
        Box a = new Box();                      // A: main's local
        a.item = new Item(1);                   // B: only A.item holds it
        Box c = build();                        // C, D: returned by build
        kept = new Box();                       // G
        kept.item = new Item(3);                // under G
        use(c, args[0]);
        System.out.println(a.item.n + c.item.n + kept.item.n);   // a and c stay live
    }

    static Box build() {
        Box x = new Box();
        x.item = new Item(2);
        return x;
    }

    static void use(Box x, String file) throws Exception {
        Item i = x.item;                        // D: held by use's i and by C.item
        Holder h = new Holder();                // H: use's local
        h.inner = new Item(4);                  // under H
        HotSpotDiagnosticMXBean mx = ManagementFactory.newPlatformMXBeanProxy(
                ManagementFactory.getPlatformMBeanServer(),
                "com.sun.management:type=HotSpotDiagnostic", HotSpotDiagnosticMXBean.class);
        mx.dumpHeap(file, true);
        System.out.println(i.n + h.inner.n + x.item.n);           // i, h, x stay live
    }
}

class Box    { Item item; }
class Holder { Item inner; }
class Item   { int n; Item(int n) { this.n = n; } }
