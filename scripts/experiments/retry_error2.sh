cd /hy-tmp/skill && nohup ./scripts/experiments/rq1.sh minimax-cn/MiniMax-M2.5 \
    --backend skillsbench \
    --early-stop-intra-attempt \
    --max-parallel-tasks 2 \
    --skillsbench-task-path tasks/fix-druid-loophole-cve,tasks/setup-fuzzing-py,tasks/suricata-custom-exfil,tasks/syzkaller-ppdev-syzlang,tasks/mario-coin-counting,tasks/organize-messy-files,tasks/pddl-tpp-planning,tasks/invoice-fraud-detection,tasks/pptx-reference-formatting \
    &> retry_error2.log &
