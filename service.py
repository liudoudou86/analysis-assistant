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
from pydantic import BaseModel

app = FastAPI(
    title="Git提交分析应用", version="0.0.1", description="Git提交分析应用接口"
)

# 解耦所有鉴权
cozeAuthorization = (
    ""
)
botId = ""


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
    commitShaUpdate = commitSha[:9]
    url = f"https://oapi.dingtalk.com/robot/send?access_token={dingdingToken}&timestamp={timestamp}&sign={sign}"
    print(f"请求地址: {url}")
    dd = DingDing(webhook=url)
    try:
        ddInfo = dd.Send_MardDown_Msg(
            Title=title,
            Content=f"### {title}:\n\n"
            f"##### [项目名称]: {projectName}\n\n"
            f"##### [触发分支]: [{commitName}](http://idp-gitlab.tasly.com/qa/automation/apis/{projectName}/tree/{commitName})\n\n"
            f"##### [触发提交]: [{commitShaUpdate}](http://idp-gitlab.tasly.com/qa/automation/apis/{projectName}/commit/{commitSha})\n\n"
            "---\n\n"
            "#### Commit分析结果 ⬇\n\n"
            f"{message}\n\n"
            "@13820303577 @18622653082",
            atMobiles=["+86-13820303577", "+86-18622653082"],
            isAtAll=False,
        )
        print(f"钉钉发送成功: {ddInfo}")
    except Exception as e:
        print(f"钉钉错误信息: {e}")


# 请求体
class CommitInfo(BaseModel):
    dingdingSecret: str
    dingdingToken: str
    projectName: str
    commitName: str
    commitSha: str
    gitLog: str


# 接口服务
@app.post("/analysis/", response_model=dict, responses={500: {"model": dict}})
async def process_commit(commitInfo: CommitInfo):
    try:
        dingdingSecret = commitInfo.dingdingSecret
        dingdingToken = commitInfo.dingdingToken
        projectName = commitInfo.projectName
        commitName = commitInfo.commitName
        commitSha = commitInfo.commitSha
        gitLog = commitInfo.gitLog

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
    except ValueError as e:
        print(f"接口错误信息: {e}")
        return {"code": 500, "result": "fail"}


if __name__ == "__main__":
    uvicorn.run("service:app", host="10.6.0.116", port=15001, reload=True)
