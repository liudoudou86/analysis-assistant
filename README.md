### 代码分析助手

- 打包成功后自动将git日志推送至接口服务
- 调用Bot分析git日志并输出测试大纲
- 将分析结果推送至钉钉提醒

```
# 安装第三方库
pip install -r requirements.txt

# gitlab-ci.yml
stages:
  - git-log-analysis

git-log-analysis:
  stage: git-log-analysis
  variables: 
    DINGDING_SECRET: SEC08ded2084e63fb60960d89d672f0e15b31f04ef337c2596d0b76a4a319db907c
    DINGDING_TOKEN: fe99910d773622ba63f910ff57c005a8fa48fc054d6e333e8508614d72cf68d6
  when: on_success
  script:
    - echo "Git-Log-Analysis by ${CI_PROJECT_NAME}-${CI_COMMIT_REF_NAME}-${CI_COMMIT_SHA}"
    - gitLog=$(git log -p -1)
    - curl -X POST "http://10.6.0.116:15001/analysis/" 
    -H "Content-Type: application/json" 
    -d "{
      \"dingdingSecret\": \"$DINGDING_SECRET\", 
      \"dingdingToken\": \"$DINGDING_TOKEN\",
      \"projectName\": \"$CI_PROJECT_NAME\",
      \"commitName\": \"$CI_COMMIT_REF_NAME\",
      \"commitSha\": \"$CI_COMMIT_SHA\",
      \"message\": \"$gitLog\",
      }"
  only:
    - develop
```
