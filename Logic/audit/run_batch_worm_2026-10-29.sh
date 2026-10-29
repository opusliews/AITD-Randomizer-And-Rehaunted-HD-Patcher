#!/bin/sh
# Worm rule (v25, 2026-10-29): v24 seeds checked by the v25 logic (5/3 -> 5/2 needs worm_lured),
# then v25 itself (must never fail). The old generator sits at Generated/_old/v24/Generated.
cd /c/Projects/AITD/Research
OUT=../Generated/Seeds/_batch_worm
mkdir -p $OUT
B=../Generated/Logic/audit/batch_full.py
for P in extreme default; do
  echo "=== v24 generate $P ==="
  BATCH_GENERATE_DIR='C:\Projects\AITD\Generated\_old\v24\Generated\Generator' \
    python $B generate --seeds 1-30 --preset $P --save $OUT/v24_$P > $OUT/v24_$P.txt 2> $OUT/v24_$P.err
  tail -2 $OUT/v24_$P.txt
  echo "=== v25 logic checks v24 $P ==="
  python $B check --seeds 1-30 --preset $P --dir $OUT/v24_$P > $OUT/check_v24_$P.txt 2> $OUT/check_v24_$P.err
  tail -3 $OUT/check_v24_$P.txt
  echo "=== v25 generate $P ==="
  python $B generate --seeds 1-30 --preset $P > $OUT/v25_$P.txt 2> $OUT/v25_$P.err
  tail -2 $OUT/v25_$P.txt
done
echo "=== DONE ==="
