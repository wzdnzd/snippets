#!/usr/bin/env bash
set -uo pipefail

# dangling: 仅清理悬空镜像
# all:      清理所有未被任何容器引用的镜像
# none:     不清理镜像
PRUNE_MODE="${PRUNE_MODE:-dangling}"

updated=0
unchanged=0
skipped=0
failed=0

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

# ========== 解析命令行参数 ==========
SKIP_IMAGES=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-images)
            if [[ -z "${2:-}" ]]; then
                log "错误：--skip-images 需要一个逗号分隔的镜像名或关键字参数"
                exit 1
            fi
            SKIP_IMAGES="$2"
            shift 2
            ;;
        --help|-h)
            echo "用法：$0 [--skip-images <镜像1,镜像2,...>]"
            echo "  --skip-images  指定跳过检查升级的镜像，可以是全名或关键字，逗号分隔"
            exit 0
            ;;
        *)
            log "错误：未知参数：$1"
            echo "用法：$0 [--skip-images <镜像1,镜像2,...>]"
            exit 1
            ;;
    esac
done
# ========== 参数解析结束 ==========

for cmd in docker python3; do
    command -v "$cmd" >/dev/null 2>&1 || {
        log "错误：缺少命令：$cmd"
        exit 1
    }
done

docker info >/dev/null 2>&1 || {
    log '错误：无法连接 Docker Daemon'
    exit 1
}

docker compose version >/dev/null 2>&1 || {
    log '错误：需要 Docker Compose V2'
    exit 1
}

case "$PRUNE_MODE" in
    dangling|all|none) ;;
    *)
        log "错误：PRUNE_MODE 只能是 dangling、all 或 none"
        exit 1
        ;;
esac

# 防止同一脚本并发运行；系统没有 flock 时自动跳过加锁
exec 9>"${LOCK_FILE:-/tmp/compose-update-running.lock}"
if command -v flock >/dev/null 2>&1 && ! flock -n 9; then
    log '已有更新任务正在运行，本次退出'
    exit 0
fi

declare -A services=()
separator=$'\x1e'
format='{{with index .Config.Labels "com.docker.compose.project"}}{{.}}{{end}}{{"\u001e"}}{{with index .Config.Labels "com.docker.compose.service"}}{{.}}{{end}}{{"\u001e"}}{{with index .Config.Labels "com.docker.compose.project.working_dir"}}{{.}}{{end}}{{"\u001e"}}{{with index .Config.Labels "com.docker.compose.project.config_files"}}{{.}}{{end}}{{"\u001e"}}{{with index .Config.Labels "com.docker.compose.oneoff"}}{{.}}{{end}}'

mapfile -t container_ids < <(
    docker ps -q \
        --filter 'label=com.docker.compose.project' \
        --filter 'label=com.docker.compose.service'
)

if ((${#container_ids[@]} == 0)); then
    log '没有正在运行的 Docker Compose 容器'
    exit 0
fi

for container_id in "${container_ids[@]}"; do
    metadata="$(docker inspect --format "$format" "$container_id" 2>/dev/null)" || continue
    IFS="$separator" read -r project service working_dir config_files oneoff <<< "$metadata"

    [[ "$oneoff" == 'True' || "$oneoff" == 'true' ]] && continue
    [[ -n "$project" && -n "$service" ]] || continue

    key="${project}"$'\x1f'"${service}"$'\x1f'"${working_dir}"$'\x1f'"${config_files}"
    services["$key"]=1
done

for key in "${!services[@]}"; do
    IFS=$'\x1f' read -r project service working_dir config_files <<< "$key"
    log "检查：$project / $service"

    if [[ -z "$working_dir" || ! -d "$working_dir" ]]; then
        log "跳过：Compose 工作目录不存在：${working_dir:-<空>}"
        ((skipped++))
        continue
    fi

    compose=(docker compose --project-directory "$working_dir" -p "$project" --profile '*')
    config_ok=1

    if [[ -n "$config_files" ]]; then
        IFS=',' read -r -a files <<< "$config_files"
        for file in "${files[@]}"; do
            [[ "$file" == /* ]] || file="$working_dir/$file"
            if [[ ! -f "$file" ]]; then
                log "跳过：Compose 配置文件不存在：$file"
                config_ok=0
                break
            fi
            compose+=(-f "$file")
        done
    fi

    if ((config_ok == 0)); then
        ((skipped++))
        continue
    fi

    if ! config_json="$(cd "$working_dir" && "${compose[@]}" config --format json)"; then
        log '失败：无法解析 Compose 配置'
        ((failed++))
        continue
    fi

    desired_image="$(
        printf '%s' "$config_json" |
        python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("services",{}).get(sys.argv[1],{}).get("image","") or "")' "$service"
    )" || {
        log '失败：无法读取服务的 image 配置'
        ((failed++))
        continue
    }

    if [[ -z "$desired_image" ]]; then
        log '跳过：该服务没有 image 配置，可能是本地 build 服务'
        ((skipped++))
        continue
    fi

    # ========== 新增：检查是否匹配跳过列表 ==========
    skip_this=0
    if [[ -n "$SKIP_IMAGES" ]]; then
        IFS=',' read -r -a skip_array <<< "$SKIP_IMAGES"
        for skip in "${skip_array[@]}"; do
            # 去除首尾空格
            skip="${skip#"${skip%%[![:space:]]*}"}"
            skip="${skip%"${skip##*[![:space:]]}"}"
            [[ -z "$skip" ]] && continue
            if [[ "$desired_image" == "$skip" || "$desired_image" == *"$skip"* ]]; then
                log "跳过：镜像 $desired_image 匹配跳过关键字 '$skip'"
                skip_this=1
                break
            fi
        done
    fi
    if ((skip_this)); then
        ((skipped++))
        continue
    fi
    # ========== 跳过检查结束 ==========

    mapfile -t running_ids < <(
        docker ps -q \
            --filter "label=com.docker.compose.project=$project" \
            --filter "label=com.docker.compose.service=$service" \
            --filter 'label=com.docker.compose.oneoff=False'
    )

    if ((${#running_ids[@]} == 0)); then
        log '跳过：该服务当前已不再运行'
        ((skipped++))
        continue
    fi

    mapfile -t old_image_ids < <(
        docker inspect --format '{{.Image}}' "${running_ids[@]}" 2>/dev/null | sort -u
    )

    if ((${#old_image_ids[@]} == 0)); then
        log '失败：无法取得当前容器镜像 ID'
        ((failed++))
        continue
    fi

    log "拉取：$desired_image"
    if ! (cd "$working_dir" && "${compose[@]}" pull --policy always "$service"); then
        log '失败：镜像拉取失败，当前容器保持不变'
        ((failed++))
        continue
    fi

    new_image_id="$(docker image inspect --format '{{.Id}}' "$desired_image" 2>/dev/null || true)"
    if [[ -z "$new_image_id" ]]; then
        log '失败：无法取得拉取后的镜像 ID'
        ((failed++))
        continue
    fi

    image_changed=0
    for old_image_id in "${old_image_ids[@]}"; do
        [[ "$old_image_id" == "$new_image_id" ]] || image_changed=1
    done

    if ((image_changed == 0)); then
        log '无需更新：已经是最新镜像'
        ((unchanged++))
        continue
    fi

    up_args=(up -d --no-deps --no-build --pull never)
    if ((${#running_ids[@]} > 1)); then
        up_args+=(--scale "$service=${#running_ids[@]}")
    fi
    up_args+=("$service")

    log "重建：旧镜像=${old_image_ids[*]}，新镜像=$new_image_id"
    if (cd "$working_dir" && "${compose[@]}" "${up_args[@]}"); then
        log '完成：服务已更新'
        ((updated++))
    else
        log '失败：服务重建失败'
        ((failed++))
    fi
done

if ((updated > 0)); then
    case "$PRUNE_MODE" in
        dangling)
            log '清理悬空旧镜像'
            docker image prune -f || ((failed++))
            ;;
        all)
            log '清理所有未被容器引用的镜像'
            docker image prune -af || ((failed++))
            ;;
        none)
            log '已跳过镜像清理'
            ;;
    esac
fi

log "汇总：已更新=$updated，无需更新=$unchanged，跳过=$skipped，失败=$failed"
((failed == 0))

# 检查并更新系统
apt update && apt upgrade -y

