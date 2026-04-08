export PATH=/usr/local/node/bin:$PATH
proxy="http://127.0.0.1:7890" # 替换为你的代理地址
export http_proxy=$proxy
export https_proxy=$proxy
export ftp_proxy=$proxy
export no_proxy="localhost,127.0.0.1,localaddress,.localdomain.com"

. "$HOME/.local/bin/env"
