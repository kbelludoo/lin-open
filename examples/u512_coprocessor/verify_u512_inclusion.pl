#!/usr/bin/env perl
# Zero-LIN LIP1 auditor in Perl (schema 1.13).
# Path walk + LRI1 identity + packed LCR2 vs SafeMath ref + packed LCR2-full
# vs FullMath ref_amount_out_full. Math::BigInt::Calc, not GMP. No LinVM.
use strict;
use warnings;
use JSON::PP;
use Digest::SHA qw(sha256);
use Math::BigInt lib => 'Calc';

my $UMAX = (Math::BigInt->bone() << 256) - 1;
my $SCHEMA = 'LIN_U512_COPROCESSOR_EVIDENCE_1.13';

sub fail {
    print "FAIL $_[0]\n";
    exit 1;
}

sub parse_int {
    my ($v) = @_;
    return Math::BigInt->new($v) if ref($v) eq 'Math::BigInt';
    $v = '0' unless defined $v;
    return Math::BigInt->new($v) if $v =~ /^-?\d+$/;
    $v =~ s/^0x//i;
    return Math::BigInt->from_hex($v);
}

sub walk {
    my ($p) = @_;
    my $rec = pack('H*', $p->{leaf_hex});
    my $h = sha256($p->{leaf_domain} . $rec);
    return 0 if unpack('H*', $h) ne $p->{leaf_sha256};
    my $sibs = $p->{siblings} || [];
    my $sides = $p->{sides} || [];
    for my $i (0 .. $#$sibs) {
        my $sib = pack('H*', $sibs->[$i]);
        my $side = int($sides->[$i]);
        my $payload = $side == 0 ? ($h . $sib) : ($sib . $h);
        $h = sha256($p->{node_domain} . $payload);
    }
    return unpack('H*', $h) eq $p->{root};
}

sub be32 {
    my ($rec, $off) = @_;
    return Math::BigInt->from_hex(unpack('H*', substr($rec, $off, 32)));
}

sub u64le {
    my ($rec, $off) = @_;
    my $n = Math::BigInt->bzero();
    for my $i (reverse 0 .. 7) {
        $n = ($n << 8) + ord(substr($rec, $off + $i, 1));
    }
    return $n;
}

sub i64le {
    my $u = u64le(@_);
    my $two63 = Math::BigInt->bone() << 63;
    my $two64 = Math::BigInt->bone() << 64;
    return $u >= $two63 ? $u - $two64 : $u;
}

sub lri1_fields {
    my ($hex) = @_;
    my $rec = pack('H*', $hex);
    return unless length($rec) == 240 && substr($rec, 0, 4) eq 'LRI1';
    return (
        be32($rec, 56) + (be32($rec, 88) << 256),
        be32($rec, 120), be32($rec, 152), be32($rec, 184),
    );
}

sub lcr2_fields {
    my ($hex) = @_;
    my $rec = pack('H*', $hex);
    return unless length($rec) == 208 && substr($rec, 0, 4) eq 'LCR2';
    return (
        be32($rec, 56), be32($rec, 88), be32($rec, 120), be32($rec, 152),
        u64le($rec, 184), i64le($rec, 192),
    );
}

sub ref_safe {
    my ($ain, $rin, $rout) = @_;
    if ($ain <= 0 || $rin <= 0 || $rout <= 0) {
        return (-1, Math::BigInt->bzero());
    }
    my $fee = $ain * 997;
    my $num = $fee * $rout;
    my $den = $rin * 1000 + $fee;
    if ($fee > $UMAX || $den > $UMAX || $num > $UMAX) {
        return (-2, Math::BigInt->bzero());
    }
    return (1, $num / $den);
}

sub ref_full {
    my ($ain, $rin, $rout) = @_;
    if ($ain <= 0 || $rin <= 0 || $rout <= 0) {
        return (-1, Math::BigInt->bzero());
    }
    my $fee = $ain * 997;
    my $den = $rin * 1000 + $fee;
    if ($fee > $UMAX || $den > $UMAX) {
        return (-2, Math::BigInt->bzero());
    }
    my $q = ($fee * $rout) / $den;
    if ($q > $UMAX) {
        return (-2, Math::BigInt->bzero());
    }
    return (1, $q);
}

fail('usage') unless @ARGV;
my $ev = JSON::PP->new->decode(do { local $/; open my $fh, '<', $ARGV[0] or die $!; <$fh> });
fail('schema') unless ($ev->{schema} || '') eq $SCHEMA;
my $proofs = $ev->{lip1_proofs} || [];
fail('proofs') if @$proofs < 34;
my %roots = (
    LNR1 => $ev->{lnr1_merkle},
    LCR2 => $ev->{lcr2_merkle},
    LCR2_FULL => $ev->{lcr2_full_merkle},
    LGE1 => $ev->{lge1_merkle},
    LRI1 => $ev->{lri1_merkle},
);
my %ri_by = map { $_->{name} => $_ } @{ $ev->{lri1_leaves} || [] };
my %lcr_by;
my $i = 0;
for my $L (@{ $ev->{lcr2_leaves} || [] }) {
    $lcr_by{ ($L->{class} || '') . '_' . $i } = $L;
    $i++;
}
my %full_by;
$i = 0;
for my $L (@{ $ev->{lcr2_full_leaves} || [] }) {
    my $cls = $L->{class} || '';
    my $name = $cls eq 'PHANTOM_APPROVE' ? 'PHANTOM_APPROVE' : "FULL_${cls}_${i}";
    $full_by{$name} = $L;
    $i++;
}
my %saw;
my ($n_ri, $n_ex, $n_ov, $n_z, $n_ovf) = (0, 0, 0, 0, 0);
my ($n_fex, $n_fov, $n_fz, $n_ffee, $n_fph) = (0, 0, 0, 0, 0);
for my $p (@$proofs) {
    fail('path ' . ($p->{tree} || '') . '/' . ($p->{name} || '')) unless walk($p);
    fail('root ' . ($p->{name} || '')) unless ($p->{root} || '') eq ($roots{ $p->{tree} } || '');
    if (($p->{tree} || '') eq 'LRI1') {
        my @fld = lri1_fields($p->{leaf_hex});
        my $st = $ri_by{ $p->{name} };
        fail('LRI1 bind ' . $p->{name}) unless @fld && $st;
        my ($n, $d, $q, $r) = @fld;
        my $a = parse_int($st->{a});
        my $b = parse_int($st->{b});
        fail('LRI1 n ' . $p->{name}) if $n != $a * $b || $n != parse_int($st->{n}) || $d != parse_int($st->{d});
        fail('LRI1 identity ' . $p->{name}) if $q * $d + $r != $n || $r >= $d || $q > $UMAX;
        $n_ri++;
    }
    if (($p->{tree} || '') eq 'LCR2') {
        my @fld = lcr2_fields($p->{leaf_hex});
        my $st = $lcr_by{ $p->{name} };
        fail('LCR2 bind ' . $p->{name}) unless @fld && $st;
        my ($ain, $rin, $rout, $aout, $steps, $status) = @fld;
        fail('LCR2 steps ' . $p->{name}) if $steps == 0 || $steps != parse_int($st->{steps}) || $status != parse_int($st->{status});
        fail('LCR2 pack ' . $p->{name}) if $ain != parse_int($st->{ain}) || $aout != parse_int($st->{aout});
        my ($rst, $ref) = ref_safe($ain, $rin, $rout);
        if ($p->{name} =~ /^EXACT_INPUT_/) {
            fail('LCR2 EXACT packed ' . $p->{name}) if $status != 1 || $rst != 1 || $aout != $ref || $aout != parse_int($st->{onchain});
            $n_ex++;
        } elsif ($p->{name} =~ /^OVERPAID_INPUT_/) {
            fail('LCR2 OVERPAID packed ' . $p->{name}) if $status != 1 || $rst != 1 || $aout != $ref || $aout == parse_int($st->{onchain});
            $n_ov++;
        } elsif ($p->{name} =~ /^GUARD_ZERO_/) {
            fail('LCR2 GUARD_ZERO packed') if $status != -1 || $rst != -1;
            $n_z++;
        } elsif ($p->{name} =~ /^GUARD_OVERFLOW_/) {
            fail('LCR2 GUARD_OVERFLOW packed') if $status != -2 || $rst != -2;
            $n_ovf++;
        } else {
            fail('LCR2 class ' . $p->{name});
        }
    }
    if (($p->{tree} || '') eq 'LCR2_FULL') {
        my @fld = lcr2_fields($p->{leaf_hex});
        my $st = $full_by{ $p->{name} };
        fail('LCR2_FULL bind ' . $p->{name}) unless @fld && $st;
        my ($ain, $rin, $rout, $aout, $steps, $status) = @fld;
        fail('LCR2_FULL steps ' . $p->{name}) if $steps == 0 || $steps != parse_int($st->{steps}) || $status != parse_int($st->{status});
        fail('LCR2_FULL pack ' . $p->{name}) if $ain != parse_int($st->{ain}) || $aout != parse_int($st->{aout});
        my ($rst_s) = ref_safe($ain, $rin, $rout);
        my ($rst_f, $ref_f) = ref_full($ain, $rin, $rout);
        if ($p->{name} =~ /^FULL_EXACT_INPUT_/) {
            fail('FULL EXACT packed ' . $p->{name}) if $status != 1 || $rst_f != 1 || $aout != $ref_f || $aout != parse_int($st->{onchain});
            $n_fex++;
        } elsif ($p->{name} =~ /^FULL_OVERPAID_INPUT_/) {
            fail('FULL OVERPAID packed ' . $p->{name}) if $status != 1 || $rst_f != 1 || $aout != $ref_f || $aout == parse_int($st->{onchain});
            $n_fov++;
        } elsif ($p->{name} eq 'PHANTOM_APPROVE') {
            fail('FULL PHANTOM packed') if $status != 1 || $rst_s != -2 || $rst_f != 1 || $aout != $ref_f;
            $n_fph++;
        } elsif ($p->{name} =~ /^FULL_GUARD_ZERO_/) {
            fail('FULL GUARD_ZERO packed') if $status != -1 || $rst_f != -1;
            $n_fz++;
        } elsif ($p->{name} =~ /^FULL_GUARD_FEE_OVERFLOW_/) {
            fail('FULL GUARD_FEE packed') if $status != -2 || $rst_f != -2;
            $n_ffee++;
        } else {
            fail('LCR2_FULL class ' . $p->{name});
        }
    }
    if (@{ $p->{siblings} || [] }) {
        my @tamp = @{ $p->{siblings} };
        my $b = pack('H*', $tamp[0]);
        substr($b, 0, 1) = chr(ord(substr($b, 0, 1)) ^ 1);
        $tamp[0] = unpack('H*', $b);
        my %q = %$p;
        $q{siblings} = \@tamp;
        fail('tamper silent ' . $p->{name}) if walk(\%q);
    }
    $saw{ $p->{name} } = 1;
}
for my $k (qw(phantom_997_rout_1997 wrap_borrow_2_x_2_255_div_umax two255_x2_div3 max_sq PHANTOM_APPROVE)) {
    fail("missing $k") unless $saw{$k};
}
fail("lri1 count $n_ri") if $n_ri < 8;
fail("lcr2 inclusion exact=$n_ex over=$n_ov z=$n_z ov=$n_ovf") if $n_ex < 3 || $n_ov < 3 || $n_z < 1 || $n_ovf < 1;
fail("lcr2_full inclusion exact=$n_fex over=$n_fov z=$n_fz fee=$n_ffee ph=$n_fph")
    if $n_fex < 3 || $n_fov < 3 || $n_fz < 1 || $n_ffee < 1 || $n_fph < 1;
print "PASS inclusion auditor\n";
print 'lip1_match ', scalar(@$proofs), "\n";
print "lri1_inclusion $n_ri\n";
print 'lcr2_inclusion ', ($n_ex + $n_ov + $n_z + $n_ovf), "\n";
print 'lcr2_full_inclusion ', ($n_fex + $n_fov + $n_fz + $n_ffee + $n_fph), "\n";
print "tamper_rejected 1\n";
exit 0;
