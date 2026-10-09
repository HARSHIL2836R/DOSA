import java.io.PrintWriter;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedFrame;
import jdk.jfr.consumer.RecordedMethod;
import jdk.jfr.consumer.RecordedStackTrace;
import jdk.jfr.consumer.RecordingFile;

/*
 * AllocWeights: sum Flight Recorder's allocation samples per allocating (method, bci) and the
 * frames below it.
 *
 *     java -cp <jfr.jar>:. AllocWeights alloc.jfr out.tsv
 *
 * An ObjectAllocationInNewTLAB event stands for its new buffer (tlabSize bytes), an
 * ObjectAllocationOutsideTLAB event for its own allocation (allocationSize). Output:
 *     <type>\t<method>\t<descriptor>\t<bci>\t<bytes>\t<events>\t<below>
 * where <below> is up to four caller frames, nearest first, each <type>;<method>;<descriptor>;<bci>,
 * joined by " < ". alloc_weight.py uses them to rebuild the names of allocation sites that library
 * inlining copied into application methods (Micro-Corpus-Log Phase 21).
 */
public class AllocWeights {
	static String frame(RecordedFrame f, String sep) {
		RecordedMethod m = f.getMethod();
		return m.getType().getName() + sep + m.getName() + sep + m.getDescriptor() + sep + f.getBytecodeIndex();
	}

	public static void main(String[] args) throws Exception {
		Map<String, long[]> w = new HashMap<>();
		long events = 0, bytes = 0, nostack = 0;
		try (RecordingFile rf = new RecordingFile(Paths.get(args[0]))) {
			while (rf.hasMoreEvents()) {
				RecordedEvent e = rf.readEvent();
				String t = e.getEventType().getName();
				long b;
				if (t.equals("jdk.ObjectAllocationInNewTLAB")) b = e.getLong("tlabSize");
				else if (t.equals("jdk.ObjectAllocationOutsideTLAB")) b = e.getLong("allocationSize");
				else continue;
				events++;
				bytes += b;
				RecordedStackTrace st = e.getStackTrace();
				String key;
				if (st == null || st.getFrames().isEmpty()) {
					nostack++;
					key = "?\t?\t?\t-1\t";
				} else {
					List<RecordedFrame> fs = st.getFrames();
					StringBuilder below = new StringBuilder();
					for (int k = 1; k < Math.min(5, fs.size()); k++) {
						if (k > 1) below.append(" < ");
						below.append(frame(fs.get(k), ";"));
					}
					key = frame(fs.get(0), "\t") + "\t" + below;
				}
				long[] a = w.computeIfAbsent(key, k -> new long[2]);
				a[0] += b;
				a[1]++;
			}
		}
		try (PrintWriter out = new PrintWriter(args[1], "UTF-8")) {
			out.print("# events " + events + " bytes " + bytes + " without stack " + nostack + "\n");
			for (Map.Entry<String, long[]> en : new TreeMap<>(w).entrySet()) {
				String[] k = en.getKey().split("\t", -1);
				out.print(k[0] + "\t" + k[1] + "\t" + k[2] + "\t" + k[3] + "\t" + en.getValue()[0] + "\t"
						+ en.getValue()[1] + "\t" + k[4] + "\n");
			}
		}
		System.out.println("events " + events + ", " + bytes + " bytes, " + w.size() + " keys, " + nostack + " without a stack");
	}
}
