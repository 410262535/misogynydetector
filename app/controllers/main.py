import uuid
from flask import Blueprint, render_template, request, redirect, url_for
from threading import Thread, Lock

from app.models.detector import load_model, main_process, get_post_stats_and_misogynistic_texts
from app.threads.crawler import scrape_profile

main_bp = Blueprint('main', __name__)

load_model()

# 全域任務狀態字典和鎖（避免多線程讀寫衝突）
task_state = {}
task_user_map = {}
task_lock = Lock()

def handle_analysis(task_id, username):
    with task_lock:
        task_state[task_id] = 'running'
    try:
        result = scrape_profile(username)
        if isinstance(result, dict) and result.get("status") == "no_posts":
            print(f"中止：帳號 {username} 沒有貼文")
            with task_lock:
                task_state[task_id] = 'no_posts'
            return
        # 執行模型主流程分析
        main_process()
        with task_lock:
            task_state[task_id] = 'done'
    except Exception as e:
        print(f"分析任務發生錯誤：{e}")
        with task_lock:
            task_state[task_id] = 'error'

@main_bp.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        username = request.form.get('username')
        if not username:
            return render_template('index.html', error="請輸入帳號")

        task_id = str(uuid.uuid4())
        with task_lock:
            task_user_map[task_id] = username
            task_state[task_id] = 'pending'

        Thread(target=handle_analysis, args=(task_id, username), daemon=True).start()

        return redirect(url_for('main.loading', task_id=task_id))

    return render_template('index.html')

@main_bp.route('/loading/<task_id>')
def loading(task_id):
    with task_lock:
        status = task_state.get(task_id)

    if status in ('done', 'no_posts', 'error'):
        return redirect(url_for('main.result', task_id=task_id))

    return render_template('loading.html')

@main_bp.route('/result/<task_id>')
def result(task_id):
    with task_lock:
        username = task_user_map.get(task_id)
        status = task_state.get(task_id)

    if not username:
        return redirect(url_for('main.index'))

    if status == 'no_posts':
        return render_template('result.html', username=username, no_posts=True)
    if status == 'error':
        return render_template('result.html', username=username, error="分析過程發生錯誤，請稍後再試。")

    stats, posts = get_post_stats_and_misogynistic_texts(username)
    return render_template('result.html', username=username, stats=stats, posts=posts)
