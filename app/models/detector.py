from transformers import AutoTokenizer, AutoModelForSequenceClassification
from app.database.db import connect_to_db, close_db_connection
import torch
import os

# Initialize the model and tokenizer (load only once)
model = None
tokenizer = None

# Loading model (we will only load model at first time)
def load_model():

    global model, tokenizer

    try:
        model_path = os.path.join(os.path.dirname(__file__),'Model','chinese_roberta_wwm_ext_5e-06_15ep_0.3dp_0.1wd')
        model = AutoModelForSequenceClassification.from_pretrained(model_path, local_files_only=True)
        tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        print('BERT loading successful.')
    except Exception as e:
        print(f'Error loading model : {e}')

# Update predict data
def update_prediction(table, id, label, confidence ,conn):
    cursor = conn.cursor()
    cursor.execute(f"""
        UPDATE {table}
        SET is_misogyny = %s, confidence = %s
        WHERE id = %s
    """, (label, confidence, id))

# Predict text's label and confident function
def predict_label(text):

    if text is None:
        return None,None
    
    inputs = tokenizer(
        text,
        return_tensors='pt',
        padding=True,
        truncation=True,
        max_length=512
    )

    with torch.no_grad():                                           # 禁止使用梯度，因為這只是在預測，並非訓練模型
        outputs = model(**inputs)                                   # 將先前 tokenizer 回傳的 inputs 餵給模型
        logits = outputs.logits                                     # Model 最後一層的線性輸出，沒有經過 softmax 計算的數值
        prediction = torch.nn.functional.softmax(logits,dim=-1)     # 將 logits 用 softmax 進行計算成機率
        label = torch.argmax(prediction,dim=1).item()               # 找出最大的值，也就是預測類別。dim=1 就是在列向量找出最大數值，而argmax會找出所在位置(索引)
        confidence = prediction[0][label].item()                    # 取出該類別的機率，作為 confidence。相當於這句話有百分之幾的機率是髒話的概念
        
        return label,confidence

# Predict text's and update to database
def predict_and_update(text, id, table_name, conn):

    label, confidence = predict_label(text)
    if label is None:
        # print('Pass because the text is empty.')
        return None
    
    # print(f"\ntext : {text} \nlabel : {label}")

    try:
        with conn.cursor() as cursor:
            update_prediction(table_name, id, label, confidence,conn)
    except Exception as e:
        print(f"Update error（ID: {id}）: {e}")

# main process
def main_process():

    conn = connect_to_db()
    if not conn:
        return None

    try:
        with conn.cursor() as cursor:
            # posts
            cursor.execute("SELECT id, post_text FROM posts WHERE is_misogyny IS NULL")
            posts = cursor.fetchall()
            for post in posts:
                predict_and_update(post['post_text'], post['id'], 'posts', conn)

            # replies
            cursor.execute("SELECT id, reply_text FROM replies WHERE is_misogyny IS NULL")
            replies = cursor.fetchall()
            for reply in replies:
                predict_and_update(reply['reply_text'], reply['id'], 'replies', conn)

        conn.commit()
        print("Update successful")

    except Exception as e:
        print(f"Update error {e}")

    finally:
        close_db_connection(conn)

# Count how many texts and how many text are misogynistic texts
def get_post_stats_and_misogynistic_texts(username):

    conn = connect_to_db()

    try:
        with conn.cursor() as cursor:

            cursor.execute("""
                SELECT 
                    SUM(total) AS total_posts,
                    SUM(misogynistic) AS misogynistic_posts
                FROM (
                    SELECT COUNT(*) AS total,
                        SUM(CASE WHEN is_misogyny = TRUE THEN 1 ELSE 0 END) AS misogynistic
                    FROM posts 
                    WHERE username = %s AND post_text IS NOT NULL AND post_text != ''
                    UNION ALL
                    SELECT COUNT(*) AS total,
                        SUM(CASE WHEN is_misogyny = TRUE THEN 1 ELSE 0 END) AS misogynistic
                    FROM replies 
                    WHERE username = %s AND reply_text IS NOT NULL AND reply_text != ''
                ) AS combined;
            """, (username, username))
            stats = cursor.fetchone()

            cursor.execute("""
                SELECT post_text AS text FROM posts 
                WHERE username = %s AND is_misogyny = TRUE AND post_text IS NOT NULL AND post_text != ''
                UNION ALL
                SELECT reply_text AS text FROM replies
                WHERE username = %s AND is_misogyny = TRUE AND reply_text IS NOT NULL AND reply_text != '';
            """, (username, username))
            posts = cursor.fetchall()

            return stats, posts
    finally:
        conn.close()
