// AsmCeilingProbe — measures the class-file major version ceiling of the ASM bundled
// inside stava/soot/sootclasses-trunk-jar-with-dependencies.jar.
//
// Why this exists: Phase 2 needs to know whether Stava can run on a current Temurin LTS.
// Reading the guard out of ClassReader's bytecode says "major > 60 throws". This turns that
// reading into an observation, without needing a JDK 17/21/25 install (which is blocked on
// this network).
//
// Method: take any real class file, rewrite bytes 6-7 (the major version, big-endian) to the
// version under test, hand the bytes to the same org.objectweb.asm.ClassReader that
// soot.asm.AsmClassProvider / AsmJava9ClassProvider use, and report what happens.
//
// Run:
//   javac -cp <sootjar> -d build/tools tools/AsmCeilingProbe.java
//   java  -cp <sootjar>:build/tools AsmCeilingProbe build/E01/E01.class

import org.objectweb.asm.ClassReader;

import java.nio.file.Files;
import java.nio.file.Paths;

public class AsmCeilingProbe {

    // major version -> the Java release that emits it
    static final int[][] CASES = {
        {52, 8}, {55, 11}, {58, 14}, {60, 16}, {61, 17}, {65, 21}, {69, 25},
    };

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("usage: AsmCeilingProbe <some.class>");
            System.exit(2);
        }
        byte[] original = Files.readAllBytes(Paths.get(args[0]));
        System.out.println("probe input : " + args[0]);
        System.out.println("its major   : " + ((original[6] & 0xff) << 8 | (original[7] & 0xff)));
        System.out.println("asm on cp   : " + ClassReader.class.getProtectionDomain()
                .getCodeSource().getLocation());
        System.out.println();
        System.out.printf("%-8s %-10s %s%n", "major", "java", "ClassReader result");
        System.out.printf("%-8s %-10s %s%n", "-----", "----", "------------------");

        for (int[] c : CASES) {
            int major = c[0], release = c[1];
            byte[] patched = original.clone();
            patched[6] = (byte) ((major >> 8) & 0xff);
            patched[7] = (byte) (major & 0xff);

            String result;
            try {
                ClassReader cr = new ClassReader(patched);
                result = "OK (accepted, name=" + cr.getClassName() + ")";
            } catch (IllegalArgumentException e) {
                result = "REJECTED: IllegalArgumentException: " + e.getMessage();
            } catch (Throwable t) {
                result = "REJECTED: " + t.getClass().getName() + ": " + t.getMessage();
            }
            System.out.printf("%-8d %-10s %s%n", major, ("Java " + release), result);
        }
    }
}
