#!/bin/sh
# Full seed batch (Handoff_2026-10-28): v18 extreme/default, then old v17 seeds checked by today's logic.
cd /c/Projects/AITD/Research
OUT=../Generated/Seeds/_batch
mkdir -p $OUT
B=../Generated/Logic/audit/batch_full.py
# the old generator must sit in a folder named Generated (its paths use parents[2]/Generated):
# git worktree at Generated/_old/v17/Generated. SKIP_V18=1 runs only the v17 part.
[ -n "$SKIP_V18" ] || for P in extreme default; do
  echo "=== v18 generate $P ==="
  python $B generate --seeds 1-50 --preset $P > $OUT/v18_$P.txt 2> $OUT/v18_$P.err
  tail -5 $OUT/v18_$P.txt
done
for P in extreme default; do
  echo "=== v17 generate $P ==="
  AITD_RANDO_DATA='C:\Projects\AITD\Generated\ResearchRun\SourceCopy' BATCH_GENERATE_DIR='C:\Projects\AITD\Generated\_old\v17\Generated\Generator' \
    python $B generate --seeds 1-50 --preset $P --save $OUT/old_$P > $OUT/v17_$P.txt 2> $OUT/v17_$P.err
  tail -5 $OUT/v17_$P.txt
  echo "=== v18 logic checks v17 $P ==="
  python $B check --seeds 1-50 --preset $P --dir $OUT/old_$P > $OUT/check_v17_$P.txt 2> $OUT/check_v17_$P.err
  tail -8 $OUT/check_v17_$P.txt
  echo "=== v18 logic without the spray rule checks v17 $P ==="
  python $B check --seeds 1-50 --preset $P --dir $OUT/old_$P --no-spray-rule > $OUT/check_v17_nospray_$P.txt 2> $OUT/check_v17_nospray_$P.err
  tail -8 $OUT/check_v17_nospray_$P.txt
done
echo "=== DONE ==="
