// Independent Java BigInteger oracle (not TCB). JVM stdlib only.
// FullMath width (512-bit product), not CRT/mulmod. Remainder identity q*d+r==n.
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.math.BigInteger;

class U512JavaOracle {
    static final BigInteger ONE = BigInteger.ONE;
    static final BigInteger UMAX = ONE.shiftLeft(256).subtract(ONE);

    static BigInteger parseHex(String s) {
        if (s.startsWith("0x") || s.startsWith("0X")) s = s.substring(2);
        if (s.isEmpty()) return BigInteger.ZERO;
        return new BigInteger(s, 16);
    }

    static String hex32(BigInteger n) {
        if (n.signum() < 0) {
            System.err.println("negative");
            System.exit(1);
        }
        String x = n.toString(16);
        if (x.length() > 64) x = x.substring(x.length() - 64);
        StringBuilder sb = new StringBuilder(64);
        for (int i = x.length(); i < 64; i++) sb.append('0');
        sb.append(x);
        return sb.toString();
    }

    static final class QR {
        int st;
        BigInteger q, r;
        QR(int st, BigInteger q, BigInteger r) { this.st = st; this.q = q; this.r = r; }
    }

    static QR muldiv(BigInteger a, BigInteger b, BigInteger d) {
        BigInteger z = BigInteger.ZERO;
        if (d.signum() == 0) return new QR(-1, z, z);
        BigInteger n = a.multiply(b);
        BigInteger[] qr = n.divideAndRemainder(d);
        if (qr[0].compareTo(UMAX) > 0) return new QR(-2, z, z);
        BigInteger chk = qr[0].multiply(d).add(qr[1]);
        if (chk.compareTo(n) != 0 || qr[1].compareTo(d) >= 0) {
            System.err.println("FAIL remainder identity");
            System.exit(1);
        }
        return new QR(1, qr[0], qr[1]);
    }

    static int selftest() {
        QR md = muldiv(BigInteger.valueOf(7), BigInteger.valueOf(9), BigInteger.valueOf(2));
        if (md.st != 1 || !md.q.equals(BigInteger.valueOf(31)) || !md.r.equals(ONE)) {
            System.err.println("FAIL 7*9/2");
            return 1;
        }
        BigInteger n = UMAX.multiply(UMAX);
        BigInteger lo = n.and(UMAX);
        BigInteger hi = n.shiftRight(256);
        if (!lo.equals(ONE) || !hi.equals(UMAX.subtract(ONE))) {
            System.err.println("FAIL max^2");
            return 1;
        }
        BigInteger a = ONE.shiftLeft(255);
        md = muldiv(a, BigInteger.valueOf(2), BigInteger.valueOf(3));
        BigInteger wantQ = new BigInteger("5555555555555555555555555555555555555555555555555555555555555555", 16);
        if (md.st != 1 || !md.r.equals(ONE) || !md.q.equals(wantQ)) {
            System.err.println("FAIL 2^255*2/3");
            return 1;
        }
        if (muldiv(ONE, ONE, BigInteger.ZERO).st != -1) {
            System.err.println("FAIL d=0");
            return 1;
        }
        if (muldiv(a, BigInteger.valueOf(2), ONE).st != -2) {
            System.err.println("FAIL q overflow");
            return 1;
        }
        md = muldiv(BigInteger.valueOf(997000), BigInteger.valueOf(20000), BigInteger.valueOf(10997000));
        if (md.st != 1 || !md.q.equals(BigInteger.valueOf(1813))) {
            System.err.println("FAIL 1813");
            return 1;
        }
        BigInteger two256 = ONE.shiftLeft(256);
        if (two256.compareTo(UMAX) < 0 || UMAX.compareTo(two256) >= 0) {
            System.err.println("FAIL ge512");
            return 1;
        }
        System.out.println("SELFTEST_PASS java_bigint q*d+r==n ge512");
        return 0;
    }

    static int batch() throws Exception {
        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        String line;
        int nvec = 0;
        while ((line = br.readLine()) != null) {
            line = line.trim();
            if (line.isEmpty()) continue;
            String[] p = line.split("\\s+");
            switch (p[0]) {
                case "MUL": {
                    BigInteger n = parseHex(p[1]).multiply(parseHex(p[2]));
                    System.out.println("1 " + hex32(n.and(UMAX)) + " " + hex32(n.shiftRight(256)));
                    break;
                }
                case "MULDIV": {
                    QR r = muldiv(parseHex(p[1]), parseHex(p[2]), parseHex(p[3]));
                    System.out.println(r.st + " " + hex32(r.q) + " " + hex32(r.r));
                    break;
                }
                case "GE": {
                    BigInteger a = parseHex(p[1]);
                    BigInteger b = parseHex(p[2]);
                    System.out.println(a.compareTo(b) >= 0 ? "1" : "0");
                    break;
                }
                default:
                    System.err.println("unknown op " + p[0]);
                    return 1;
            }
            nvec++;
        }
        System.err.println("BATCH_N=" + nvec + " JAVA_BIGINT_CONSENSUS");
        return 0;
    }

    public static void main(String[] args) throws Exception {
        if (args.length >= 1 && args[0].equals("--self-test")) System.exit(selftest());
        if (args.length >= 1 && args[0].equals("--batch")) System.exit(batch());
        System.err.println("usage: U512JavaOracle --self-test | --batch");
        System.exit(2);
    }
}
