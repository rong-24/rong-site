cd ~/Web/rong-site

cat > publish.sh <<'EOF'
#!/bin/bash

echo "====== 1. 进入网站目录 ======"
cd ~/Web/rong-site || exit 1

echo "====== 2. 检查本地构建是否正常 ======"
npx quartz build

if [ $? -ne 0 ]; then
  echo "构建失败，请先检查 Markdown 或配置文件。"
  exit 1
fi

echo "====== 3. 同步到 GitHub ======"
npx quartz sync

echo "====== 4. 完成 ======"
echo "如果你已经配置 Cloudflare Pages，稍后网站会自动更新。"
EOF

chmod +x publish.sh