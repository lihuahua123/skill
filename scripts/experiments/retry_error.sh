cd /hy-tmp/skill && nohup ./scripts/experiments/rq1.sh minimax-cn/MiniMax-M2.5 \
    --backend skillsbench \
    --early-stop-intra-attempt \
    --max-parallel-tasks 8 \
    --skillsbench-task-path tasks/crystallographic-wyckoff-position-analysis,tasks/mario-coin-counting,tasks/pg-essay-to-audiobook,tasks/video-silence-remover \
    &> retry_error.log &

# Skipped on purpose in local-host rerun:
# - tasks/fix-build-agentops
#   Reason: it still depends on BugSwarm image/layout beyond the env-var fix.
