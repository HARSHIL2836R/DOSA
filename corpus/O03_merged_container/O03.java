// O03: one container class used twice, once as a local and once from a static. The
// container's Node and the stored Item each come from a single allocation site, so the
// local list's elements share their abstract object with the global list's elements.
public class O03 {
    static MyList global = new MyList();    // G: reachable from a static

    public static void main(String[] args) {
        local();
        fill(global);
    }

    static void local() {
        MyList l = new MyList();            // L: local()'s own list
        fill(l);                            // its Item and Node die when local() returns
    }

    static void fill(MyList l) {
        l.add(new Item());                  // I: one site for both lists' items
    }
}

class MyList {
    Node head;
    void add(Object o) {
        Node n = new Node();                // N: one site for both lists' nodes
        n.val = o;
        n.next = head;
        head = n;
    }
}

class Node { Object val; Node next; }
class Item { }
