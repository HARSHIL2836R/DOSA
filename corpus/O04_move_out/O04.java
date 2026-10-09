// O04: ownership moves. fill() stores a new Item into main's Box; take() removes it and
// returns it, so after take() only main's local t holds the Item. take() returns a value it
// loaded from its parameter, which the borrow rule does not count as a new reference into
// main's frame. The Item must still come out owned by main's frame.
public class O04 {
    public static void main(String[] args) {
        Box b = new Box();          // A
        fill(b);                    // B is created in fill and stored into A
        Item t = take(b);           // B leaves A; only main's local t holds it
        t.n = 1;
        Holder h = new Holder();    // H
        h.keep = pass(new Item());  // P: passed down and handed straight back
    }

    static void fill(Box b)  { b.item = new Item(); }

    static Item take(Box b) {
        Item i = b.item;
        b.item = null;
        return i;
    }

    static Item pass(Item i) { return i; }
}

class Box    { Item item; }
class Holder { Item keep; }
class Item   { int n; }
