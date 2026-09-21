public class M01 {

    static Box published;                  // the escape route: a static field

    public static void main(String[] args) {
        // group 1 — stays local, nothing can observe it
        Box kept = new Box();
        Item tucked = new Item();
        kept.item = tucked;

        // group 2 — same shape as group 1, but the container is published
        Box leaked = new Box();
        Item exposed = new Item();
        leaked.item = exposed;
        published = leaked;

        // group 3 — a two-object cycle, neither one published
        Node p = new Node();
        Node q = new Node();
        p.next = q;
        q.next = p;
    }
}

class Box  { Item item; }
class Item { }
class Node { Node next; }
