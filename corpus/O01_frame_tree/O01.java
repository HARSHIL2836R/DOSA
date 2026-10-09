// O01: one tree per frame. A local Box holding an Item, a factory whose Box and Item are
// returned to main, and a callee that only reads (borrows) what main owns.
public class O01 {
    public static void main(String[] args) {
        Box b = new Box();          // A: main's own Box
        b.item = new Item();        // B: main's own Item, stored into A
        Box c = build();            // C, D come back from build
        use(c);                     // use reads c.item and writes a field of it
    }

    static Box build() {
        Box x = new Box();          // C: allocated in build, returned
        x.item = new Item();        // D: allocated in build, reachable from C
        return x;
    }

    static void use(Box x) {
        Item i = x.item;            // a load: borrowed, not owned by use
        i.n = 1;
    }
}

class Box  { Item item; }
class Item { int n; }
