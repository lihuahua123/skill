 - crystallographic-wyckoff-position-analysis
    原因是本地 runner 之前没复现 COPY *.cif /root/cif_files/，现在会补上
  - mario-coin-counting
    会补 opencv-python、pandas
  - pg-essay-to-audiobook
    会补 jiwer、openai
  - video-silence-remover
    会补 numpy、scipy、pytest
  - fix-build-agentops
    至少把之前缺的 REPO_ID env 注入修了，但这个任务整体我仍建议跳过

  建议直接舍弃的重任务是：

  - fix-build-agentops
    依赖 BugSwarm 镜像/目录布局，本地 host 模式很难完整复现
  - fix-erlang-ssh-cve
    需要 OTP 编译、SSH 服务和系统级依赖
  - mhc-layer-impl
    需要重 PyTorch/Modal 训练栈
  - organize-messy-files
    需要大批预下载论文和 office/pdf 系统包
  - lean4-proof
    需要 Lean toolchain 安装和 baseline build