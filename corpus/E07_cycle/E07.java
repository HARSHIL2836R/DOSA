public class E07 {

    public static void main(String[] args) {
        Node a = new Node();
        Node b = new Node();
        a.next = b;
        b.next = a;            // the cycle. Nothing escapes.
    }
}

class Node { Node next; }
