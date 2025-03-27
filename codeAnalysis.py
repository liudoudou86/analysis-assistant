import base64
import hashlib
import hmac
import logging
import re
import time
import urllib.parse
from typing import Dict

import requests
import urllib3
import uvicorn
from DingDingBot.DDBOT import DingDing
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 设置全局 SSL 验证
requests.packages.urllib3.disable_warnings()

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# FastAPI 应用配置
app = FastAPI(title="Git提交分析应用", version="1.0.0", description="Git提交分析应用")

# Bot配置
BOT_ID = "7419121331410616370"
COZE_API_URL = "https://api.coze.cn/v3/chat"
DINGTALK_API_URL = "https://oapi.dingtalk.com/robot/send"

# 预编译正则表达式
ANSWER_PATTERN = re.compile(r'"type":"answer".*?"content":"(.*?)"')


class CozeAPI:
    def __init__(self, authorization: str):
        self.headers = {
            "Authorization": f"Bearer {authorization}",
            "Content-Type": "application/json",
        }

    def create_conversation(self, message: str) -> requests.Response:
        """创建会话并发送消息"""
        try:
            payload = {
                "bot_id": BOT_ID,
                "user_id": "DD9527",
                "stream": True,
                "auto_save_history": True,
                "additional_messages": [
                    {"role": "user", "content": message, "content_type": "text"}
                ],
            }
            logger.info(
                f"Coze API请求参数: URL={COZE_API_URL}, Headers={self.headers}, Payload={payload}"
            )

            # 添加 SSL 验证配置
            response = requests.post(
                url=COZE_API_URL,
                headers=self.headers,
                json=payload,
                stream=True,
                timeout=30,
                verify=False,  # 禁用 SSL 验证
                proxies={"http": None, "https": None},  # 禁用代理
            )

            # 添加响应状态码和错误信息的日志
            if response.status_code != 200:
                logger.error(
                    f"Coze API响应错误: 状态码={response.status_code}, 响应内容={response.text}"
                )

            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as e:
            logger.error(f"Coze API请求失败: {str(e)}, 错误类型: {type(e)}")
            raise HTTPException(status_code=500, detail=f"Coze API请求失败: {str(e)}")

    def get_result(self, message: str) -> str:
        """获取并处理会话结果"""
        response = self.create_conversation(message)
        contents = []

        try:
            for chunk in response.iter_content(chunk_size=1024):
                message_str = chunk.decode("utf-8", errors="ignore")
                matches = ANSWER_PATTERN.findall(message_str)
                contents.extend(match.replace("\\n", "\n") for match in matches)

            return "".join(contents)
        except Exception as e:
            logger.error(f"处理响应数据失败: {str(e)}")
            raise HTTPException(status_code=500, detail="处理响应数据失败")


class DingTalkNotifier:
    def __init__(self, secret: str, token: str):
        self.secret = secret
        self.token = token

    def create_sign(self) -> tuple:
        """生成钉钉签名"""
        timestamp = str(round(time.time() * 1000))
        secret_enc = self.secret.encode("utf-8")
        string_to_sign = f"{timestamp}\n{self.secret}"
        string_to_sign_enc = string_to_sign.encode("utf-8")
        hmac_code = hmac.new(
            secret_enc, string_to_sign_enc, digestmod=hashlib.sha256
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return timestamp, sign

    def send_message(self, notification_data: Dict) -> None:
        """发送钉钉通知"""
        timestamp, sign = self.create_sign()
        url = (
            f"{DINGTALK_API_URL}?access_token={self.token}"
            f"&timestamp={timestamp}&sign={sign}"
        )

        try:
            # 只使用基本参数初始化 DingDing
            dd = DingDing(webhook=url)

            # 修改 DingDing 实例的 session 配置
            dd.session.verify = False
            if hasattr(dd.session, "proxies"):
                dd.session.proxies = {"http": None, "https": None}

            content = self._format_message_content(notification_data)

            response = dd.Send_MardDown_Msg(
                Title=notification_data["title"],
                Content=content,
                atMobiles=["+86-13820303577", "+86-18622653082"],
                isAtAll=False,
            )

            if isinstance(response, dict) and response.get("status") is False:
                error_msg = f"钉钉消息发送失败: {response.get('message')}"
                logger.error(error_msg)
                raise Exception(error_msg)

            logger.info(f"钉钉消息发送成功: {response}")

        except Exception as e:
            logger.error(f"钉钉消息发送失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"钉钉消息发送失败: {str(e)}")

    def _format_message_content(self, data: Dict) -> str:
        """格式化钉钉消息内容"""
        return (
            f"## {data['title']}:\n"
            f"|[**项目名称**]: {data['project_name']}\n\n"
            f"|[**触发分支**]: [{data['commit_name']}]({data['project_url']}/tree/{data['commit_name']})\n\n"
            f"|[**触发提交**]: [{data['commit_sha'][:9]}]({data['project_url']}/commit/{data['commit_sha']})\n\n"
            f"|[**提交信息**]: {data['commit_message']}\n\n"
            f"|[**提交人员**]: {data['commit_user']}\n\n"
            "\n***\n\n"
            "#### COMMIT分析结果 ⬇\n\n"
            f"{data['message']}\n\n"
            "@13820303577 @18622653082"
        )


class CommitInfo(BaseModel):
    """请求体模型"""

    cozeAuthorization: str = Field(..., description="Coze API授权token")
    dingdingSecret: str = Field(..., description="钉钉密钥")
    dingdingToken: str = Field(..., description="钉钉访问token")
    projectName: str = Field(..., description="项目名称")
    projectUrl: str = Field(..., description="项目URL")
    commitName: str = Field(..., description="提交分支")
    commitSha: str = Field(..., description="提交SHA")
    commitMessage: str = Field(..., description="提交信息")
    commitUser: str = Field(..., description="提交用户")
    gitLog: str = Field(..., description="Git日志")


@app.post(
    "/analysis/",
    response_model=Dict[str, str],
    responses={
        200: {"description": "分析成功"},
        500: {"description": "服务器内部错误"},
    },
)
async def process_commit(commit_info: CommitInfo) -> Dict[str, str]:
    """处理Git提交分析请求"""
    try:
        # 初始化服务
        coze_api = CozeAPI(commit_info.cozeAuthorization)
        notifier = DingTalkNotifier(
            commit_info.dingdingSecret, commit_info.dingdingToken
        )

        # 获取分析结果
        analysis_result = coze_api.get_result(commit_info.gitLog)

        # 发送钉钉通知
        notification_data = {
            "title": "Git-Commit Analysis",
            "project_name": commit_info.projectName,
            "project_url": commit_info.projectUrl,
            "commit_name": commit_info.commitName,
            "commit_sha": commit_info.commitSha,
            "commit_message": commit_info.commitMessage,
            "commit_user": commit_info.commitUser,
            "message": analysis_result,
        }
        notifier.send_message(notification_data)

        return {"code": "0", "result": "success"}

    except Exception as e:
        logger.error(f"处理请求失败: {str(e)}", exc_info=True)
        return {"code": "500", "result": str(e)}


if __name__ == "__main__":
    uvicorn.run(
        "codeAnalysis:app", host="127.0.0.1", port=15001, reload=True, log_level="info"
    )
