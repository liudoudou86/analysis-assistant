from fastapi import FastAPI
import uvicorn
import requests
import re
from DingDingBot.DDBOT import DingDing
import time
import hmac
import hashlib
import base64
import urllib.parse

app = FastAPI()

# 解耦所有鉴权
cozeAuthorization = "个人令牌"
botId = "机器人ID"


# 扣子Bot请求接口
def createConversation(message):
    url = "https://api.coze.cn/v3/chat"
    headers = {
        "Authorization": "Bearer " + cozeAuthorization,
        "Content-Type": "application/json",
    }
    json = {
        "bot_id": botId,
        "user_id": "DD9527",
        "stream": True,
        "auto_save_history": True,
        "additional_messages": [
            {"role": "user", "content": message, "content_type": "text"}
        ],
    }
    response = requests.post(url=url, headers=headers, json=json, stream=True)
    print(response.text)
    return response


# 提取返回内容
def getResult(message):
    response = createConversation(message)
    contents = []

    # 遍历流式报文数据
    for chunk in response.iter_content(chunk_size=1024):
        message_str = chunk.decode("utf-8", errors="ignore")
        # 查找所有type为'answer'的报文
        matches = re.findall(r'"type":"answer".*?"content":"(.*?)"', message_str)
        for match in matches:
            content = match.replace("\\n", "\n")
            contents.append(content)

    # 拼接所有提取的content值
    complete_content = "".join(contents)
    return complete_content


# 钉钉加签
def createSign(dingdingSecret):
    timestamp = str(round(time.time() * 1000))
    secret = dingdingSecret
    secret_enc = secret.encode("utf-8")
    string_to_sign = "{}\n{}".format(timestamp, secret)
    string_to_sign_enc = string_to_sign.encode("utf-8")
    hmac_code = hmac.new(
        secret_enc, string_to_sign_enc, digestmod=hashlib.sha256
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return timestamp, sign


# 推送钉钉提醒
def send_msg(
    dingdingSecret, dingdingToken, projectName, commitName, commitSha, title, message
):
    timestamp, sign = createSign(dingdingSecret)
    url = f"https://oapi.dingtalk.com/robot/send?access_token={dingdingToken}&timestamp={timestamp}&sign={sign}"
    dd = DingDing(webhook=url)
    try:
        dd.Send_MardDown_Msg(
            Title=title,
            Content=f"### {title}:\n\n"
            f"##### [项目名称]: {projectName}\n\n"
            f"##### [分支名称]: {commitName}\n\n"
            f"##### [分支版本]: {commitSha}\n\n"
            "---\n\n"
            "#### Commit分析结果 ⬇\n\n"
            f"{message}\n\n"
            "@手机号",
            atMobiles=["+86-手机号"],
            isAtAll=False,
        )
    except Exception as e:
        print(f"钉钉错误信息: {e}")


# 接口服务
@app.post("/analysis/")
async def process_commit(
    dingdingSecret: str,
    dingdingToken: str,
    projectName: str,
    commitName: str,
    commitSha: str,
    gitLog: str,
):
    try:
        message = getResult(gitLog)
        send_msg(
            dingdingSecret,
            dingdingToken,
            projectName,
            commitName,
            commitSha,
            "Git-Commit Analysis",
            message,
        )
        return {"code": 0, "result": "success"}
    except Exception as e:
        print(f"接口错误信息: {e}")
        return {"code": 500, "result": "fail"}


if __name__ == "__main__":
    uvicorn.run("service:app", host="127.0.0.1", port=8888, reload=True)
