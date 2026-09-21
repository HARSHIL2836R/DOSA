public class M02 {

    static Box published;

    public static void main(String[] args) {
        Box a = makeBox();          // factory: one allocation site,
        Item i = new Item();
        fill(a, i);                 // store into a field of a parameter

        Box b = makeBox();          // ... two different owners
        Item j = new Item();
        fill(b, j);
        publish(b);                 // escapes, but only inside the callee

        Node p = new Node();        // a two-object cycle, entirely local
        Node q = new Node();
        p.next = q;
        q.next = p;
    }

    static Box  makeBox()               { return new Box(); }
    static void fill(Box box, Item it)  { box.item = it; }
    static void publish(Box box)        { published = box; }
}

class Box  { Item item; }
class Item { }
class Node { Node next; }
