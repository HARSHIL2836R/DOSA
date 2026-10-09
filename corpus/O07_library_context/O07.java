import java.util.Iterator;
import java.util.LinkedList;

// O07: a JDK allocation shared by every caller. LinkedList.listIterator allocates the iterator
// inside the JDK, so Spark has one ListItr for the whole program. walk() drops its iterator when
// it returns; keep() stores one in a static. Without context both are the same abstract object,
// so both are HEAP. Library inlining copies listIterator's allocation into each caller.
public class O07 {
    static Iterator<Integer> kept;

    public static void main(String[] args) {
        LinkedList<Integer> list = new LinkedList<Integer>();   // L
        list.add(1);
        walk(list);
        keep(list);
    }

    static int walk(LinkedList<Integer> l) {
        int s = 0;
        for (Iterator<Integer> it = l.listIterator(0); it.hasNext(); )   // dies with walk
            s += it.next();
        return s;
    }

    static void keep(LinkedList<Integer> l) {
        kept = l.listIterator(0);                                        // published
    }
}
