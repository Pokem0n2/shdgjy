#!/usr/bin/env bash
# shdgjy APK 构建（aarch64 主机，box64 跑 x86_64 工具链）
# 用法：apk/build.sh <versionName> <versionCode>   例如 apk/build.sh 0.1.0 1
# d8/apksigner 是 bash 包装（内部 java -jar），绝不进 box64；aapt2/aapt/zipalign 是 ELF 必须 box64
set -euo pipefail
VER_NAME="${1:?usage: build.sh <versionName> <versionCode>}"
VER_CODE="${2:?}"
SDK="$HOME/android-sdk"
JAR="$SDK/platforms/android-34/android.jar"
BT="$SDK/build-tools/34.0.0"
APKDIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$(dirname "$APKDIR")/dist"
B="$APKDIR/build"
rm -rf "$B"; mkdir -p "$B/obj" "$B/dex" "$B/compiled" "$OUT"

echo "[1/7] javac"
# 必须用 JDK8 编译：系统 javac 21 生成的嵌套类元数据会触发 d8(R8 8.2.2-dev) 内部 NPE
J8BIN="/usr/lib/jvm/java-8-openjdk-arm64/bin"
"$J8BIN/javac" -source 8 -target 8 -bootclasspath "$JAR" -d "$B/obj" "$APKDIR/src/com/yzz/shdgjy/MainActivity.java"

echo "[2/7] d8"
# d8.jar 需要新版 JVM 运行（java8 跑不动），但输入必须来自 javac8 的产物
bash "$BT/d8" --output "$B/dex" --min-api 21 --lib "$JAR" --release "$B"/obj/com/yzz/shdgjy/*.class

echo "[3/7] aapt2 compile"
box64 "$BT/aapt2" compile -o "$B/compiled/" --dir "$APKDIR/res" 2>&1 | grep -v 'nftw\|Reading elf header' || true

echo "[4/7] aapt2 link"
box64 "$BT/aapt2" link -o "$B/app.unsigned.apk" -I "$JAR" \
  --manifest "$APKDIR/AndroidManifest.xml" \
  --version-code "$VER_CODE" --version-name "$VER_NAME" \
  --min-sdk-version 21 --target-sdk-version 34 \
  -A "$APKDIR/assets" \
  "$B"/compiled/*.flat 2>&1 | grep -v 'nftw\|Reading elf header' || true

echo "[5/7] aapt add classes.dex"
(cd "$B/dex" && box64 "$BT/aapt" add "$B/app.unsigned.apk" classes.dex 2>&1 | grep -v 'nftw\|Reading elf header' || true)

echo "[6/7] zipalign"
box64 "$BT/zipalign" -f 4 "$B/app.unsigned.apk" "$B/app.aligned.apk" 2>&1 | grep -v 'nftw\|Reading elf header' || true

echo "[7/7] apksigner"
java -jar "$BT/lib/apksigner.jar" sign \
  --ks "$HOME/.android/debug.keystore" --ks-pass pass:android --key-pass pass:android \
  --out "$OUT/shdgjy-v${VER_NAME}.apk" "$B/app.aligned.apk"
java -jar "$BT/lib/apksigner.jar" verify "$OUT/shdgjy-v${VER_NAME}.apk" && echo "签名校验 OK"
echo "完成: $OUT/shdgjy-v${VER_NAME}.apk"
