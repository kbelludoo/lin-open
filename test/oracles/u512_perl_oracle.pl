#!/usr/bin/env perl
# Independent Perl Math::BigInt oracle (not TCB).
# Force the pure-Perl Calc backend so this is not a silent GMP wrapper.
# EXPERIMENTAL: FullMath width (512-bit product), not CRT/mulmod.
use strict;
use warnings;
use Math::BigInt lib => 'Calc';

my $UMAX = (Math::BigInt->bone() << 256) - 1;
my $ZERO = Math::BigInt->bzero();

sub parse_hex {
    my ($s) = @_;
    $s = '' unless defined $s;
    $s =~ s/^0x//i;
    $s = '0' if $s eq '';
    return Math::BigInt->from_hex($s);
}

sub hex32 {
    my ($n) = @_;
    $n = $ZERO->copy() unless defined $n;
    my $h = $n->as_hex();
    $h =~ s/^0x//;
    $h = '0' if $h eq '';
    return ('0' x (64 - length($h))) . $h if length($h) < 64;
    return substr($h, -64);
}

sub muldiv {
    my ($a, $b, $d) = @_;
    if ($d->is_zero()) {
        return (-1, $ZERO->copy(), $ZERO->copy());
    }
    my $n = $a * $b;
    my $q = $n / $d;
    my $r = $n % $d;
    if ($q > $UMAX) {
        return (-2, $ZERO->copy(), $ZERO->copy());
    }
    if ($q * $d + $r != $n || $r >= $d) {
        die "FAIL remainder identity\n";
    }
    return (1, $q, $r);
}

sub selftest {
    my ($st, $q, $r) = muldiv(Math::BigInt->new(7), Math::BigInt->new(9), Math::BigInt->new(2));
    if ($st != 1 || $q != 31 || $r != 1) {
        warn "FAIL 7*9/2\n";
        return 1;
    }
    my $n = $UMAX * $UMAX;
    my $lo = $n & $UMAX;
    my $hi = $n >> 256;
    if ($lo != 1 || $hi != $UMAX - 1) {
        warn "FAIL max^2\n";
        return 1;
    }
    my $a = Math::BigInt->bone() << 255;
    ($st, $q, $r) = muldiv($a, Math::BigInt->new(2), Math::BigInt->new(3));
    my $want = Math::BigInt->from_hex('5555555555555555555555555555555555555555555555555555555555555555');
    if ($st != 1 || $r != 1 || $q != $want) {
        warn "FAIL 2^255*2/3\n";
        return 1;
    }
    ($st) = muldiv(Math::BigInt->new(1), Math::BigInt->new(1), $ZERO->copy());
    if ($st != -1) {
        warn "FAIL d=0\n";
        return 1;
    }
    ($st) = muldiv($a, Math::BigInt->new(2), Math::BigInt->new(1));
    if ($st != -2) {
        warn "FAIL q overflow\n";
        return 1;
    }
    ($st, $q) = muldiv(Math::BigInt->new(997000), Math::BigInt->new(20000), Math::BigInt->new(10997000));
    if ($st != 1 || $q != 1813) {
        warn "FAIL 1813\n";
        return 1;
    }
    my $two256 = Math::BigInt->bone() << 256;
    if (!($two256 >= $UMAX) || ($UMAX >= $two256)) {
        warn "FAIL ge512\n";
        return 1;
    }
    my $lib = Math::BigInt->config('lib');
    if ($lib !~ /Calc/) {
        warn "FAIL backend $lib (want Calc, not GMP)\n";
        return 1;
    }
    print "SELFTEST_PASS perl_bigint q*d+r==n ge512 backend=$lib\n";
    return 0;
}

sub batch {
    my $nvec = 0;
    while (defined(my $line = <STDIN>)) {
        chomp $line;
        $line =~ s/^\s+|\s+$//g;
        next if $line eq '';
        my @p = split /\s+/, $line;
        if ($p[0] eq 'MUL') {
            my $a = parse_hex($p[1]);
            my $b = parse_hex($p[2]);
            my $n = $a * $b;
            my $lo = $n & $UMAX;
            my $hi = $n >> 256;
            printf "1 %s %s\n", hex32($lo), hex32($hi);
        } elsif ($p[0] eq 'MULDIV') {
            my ($st, $q, $r) = muldiv(parse_hex($p[1]), parse_hex($p[2]), parse_hex($p[3]));
            printf "%d %s %s\n", $st, hex32($q), hex32($r);
        } elsif ($p[0] eq 'GE') {
            my $a = parse_hex($p[1]);
            my $b = parse_hex($p[2]);
            print(($a >= $b) ? "1\n" : "0\n");
        } else {
            warn "unknown op $p[0]\n";
            return 1;
        }
        $nvec++;
    }
    print STDERR "BATCH_N=$nvec PERL_BIGINT_CONSENSUS\n";
    return 0;
}

if (($ARGV[0] || '') eq '--self-test') {
    exit selftest();
}
if (($ARGV[0] || '') eq '--batch') {
    exit batch();
}
print STDERR "usage: u512_perl_oracle.pl --self-test | --batch\n";
exit 2;
