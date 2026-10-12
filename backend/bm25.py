"""BM25 关键词检索（中文用字符二元组切分，不引分词库）。

为什么需要它：
    向量检索靠语义，对"意思相近但用词不同"友好；
    但对"精确词"反而不敏感——因为整篇文档的向量被标题语义主导，
    正文里的低频细节词（"润滑脂""皮带"）会被平均掉。

    实测证据（eval/cases_rag.json 的 rag-hard-02）：
        问题"润滑脂什么时候补？皮带松了怎么办？"
        正确文档《传送带异响排查》向量分只有 0.526，低于 0.55 阈值 → 被误判为无结果
        但 BM25 给它 7.69（该题最高），因为"润滑脂""皮带"是文档里的原词

为什么用字符二元组：
    中文没有天然空格分隔，正经做法是引 jieba 之类的分词库。
    二元组（"润滑脂" → "润滑"+"滑脂"）不需要任何依赖，对短文档召回够用。
    代价：会切出一些无意义组合，靠 IDF 自然压低它们的权重。

BM25 是什么：
    关键词检索的经典算法。核心是两件事——
    IDF：越罕见的词越有区分度（"润滑脂"比"设备"值钱得多）
    词频饱和：一个词出现 10 次不代表相关度是 1 次的 10 倍，所以要压平
"""

import math
import re

K1 = 1.5   # 词频饱和系数：越大越"奖励多次出现"，1.2~2.0 是常用区间
B = 0.75   # 长度归一化：越大越惩罚长文档，0.75 是经典默认值


def tokenize(text: str) -> list[str]:
    toks = []
    for seg in re.findall(r"[a-zA-Z0-9]+|[一-鿿]+", text):
        if seg[0].isascii():
            toks.append(seg.lower())
        else:
            toks += [seg[i:i + 2] for i in range(len(seg) - 1)] or [seg]
    return toks


def score(query: str, doc_tokens: list[list[str]]) -> list[float]:
    """给每个文档打 BM25 分。doc_tokens 是各文档预先切好的词列表。

    分数是无界的正数（常见 0~15），不能和余弦相似度直接比较——这就是
    我们另设一个 BM25_MIN_SCORE 阈值、而不是复用 MIN_SCORE 的原因。
    """
    if not doc_tokens:
        return []

    n = len(doc_tokens)
    avgdl = sum(len(d) for d in doc_tokens) / n

    df: dict[str, int] = {}
    for d in doc_tokens:
        for t in set(d):
            df[t] = df.get(t, 0) + 1

    # +1 保证 IDF 非负：一个词若在所有文档都出现，IDF 趋近 0 而不是负数
    idf = {t: math.log((n - v + 0.5) / (v + 0.5) + 1) for t, v in df.items()}

    scores = []
    for d in doc_tokens:
        s = 0.0
        for t in set(tokenize(query)):
            if t not in idf:
                continue
            f = d.count(t)
            if f == 0:
                continue
            s += idf[t] * f * (K1 + 1) / (f + K1 * (1 - B + B * len(d) / avgdl))
        scores.append(s)
    return scores
