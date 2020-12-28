import re
import boto3
from pytrends.request import TrendReq
from newsapi.newsapi_client import NewsApiClient
from datetime import datetime, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import json
import statistics

# Trendr.Trendr for local -> Trendr for Lambda
from Trendr.spiders.pull_content import ContentSpider

import scrapydo
import tweepy

crawl_urls = []
scrapydo.setup()


def topic_avg_sent(result_dict):
    for idx, val in enumerate(result_dict):
        count = 0
        avg_sentiment = 0
        sentiments = [];

        for idx_y, res in enumerate(result_dict[val]['urls']):
            if 'sentiment' in result_dict[val]['urls'][res]:
                curr_sentiment = result_dict[val]['urls'][res]['sentiment']
                if curr_sentiment != '':
                    sentiments.append(curr_sentiment)
                    count += 1
                    curr_sentiment = round(curr_sentiment * 100)
                    avg_sentiment += curr_sentiment

        if count != 0:
            avg_sentiment = avg_sentiment / count
            result_dict[val]['avg_sentiment'] = avg_sentiment

        if count > 1:
            stdev = statistics.stdev(sentiments)
            deviatedsent = []
            for sent in sentiments:
                if abs(sent - avg_sentiment / 100) < stdev:
                    deviatedsent.append(sent)

            stdmean = statistics.mean(deviatedsent)
            for idx_y, res in enumerate(result_dict[val]['urls']):
                if 'sentiment' in result_dict[val]['urls'][res]:
                    curr_sentiment = result_dict[val]['urls'][res]['sentiment']
                    if curr_sentiment not in deviatedsent:
                        del result_dict[val]['urls'][res]['sentiment']

            result_dict[val]['avg_sentiment'] = str(stdmean)

    return result_dict


def pull_content(start_urls):
    # results = []
    #
    # def crawler_results(signal, sender, item, response, spider):
    #     results.append(item)
    #
    # dispatcher.connect(crawler_results, signal=signals.item_passed)
    #
    # process = CrawlerProcess()
    # process.crawl(ContentSpider, start_urls=start_urls)
    # process.start()  # the script will block here until the crawling is finished
    #
    results = scrapydo.run_spider(ContentSpider, start_urls=start_urls)
    return results


def clean_dict(dictionary, idx_to_delete):
    del dictionary[idx_to_delete[0]]
    idx_to_delete.pop(0)

    if len(idx_to_delete) != 0:
        clean_dict(dictionary, idx_to_delete)
    else:
        return dictionary


def build_json(site):
    targetResults = {}

    if site == 'Google':
        res = pull_google_trends()
        for i in range(len(res)):
            targetResults[i + 1] = {}
            targetResults[i + 1]['topic'] = res[i + 1]
            targetResults[i + 1]['urls'] = {}

    if site == 'Twitter':
        res = pull_twitter_trends()
        for i in range(len(res)):
            targetResults[i + 1] = {}
            targetResults[i + 1]['topic'] = res[i]
            targetResults[i + 1]['urls'] = {}

    currentdate = datetime.today().strftime('%Y-%m-%d')
    fromdate = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')

    idxtodelete = []
    for idx, result in enumerate(targetResults):
        currtopic = targetResults[idx + 1]['topic']
        content = get_everything(currtopic, fromdate, currentdate)
        if len(content) > 0:
            for idx_y, content in enumerate(content):
                targetResults[idx + 1]['urls'][str(idx_y + 1)] = {}
                targetResults[idx + 1]['urls'][str(idx_y + 1)]['source'] = content['source']
                targetResults[idx + 1]['urls'][str(idx_y + 1)]['title'] = content['title']
                targetResults[idx + 1]['urls'][str(idx_y + 1)]['url'] = content['url']
                crawl_urls.append(content['url'])
        else:
            idxtodelete.append(idx + 1)

    # clean_dict(targetResults, idxtodelete)

    content_pull = pull_content(crawl_urls)
    for idx, each in enumerate(content_pull):
        content = content_pull[idx]['content']
        score = pull_sentiment(content)
        content_pull[idx]['sentiment'] = score
        del content_pull[idx]['content']

    for idx, each in enumerate(targetResults):
        urls = targetResults[idx + 1]['urls']
        for idx_y, url in enumerate(urls):
            for idx_z, curr in enumerate(content_pull):
                if content_pull[idx_z]['url'] == urls[str(idx_y + 1)]['url']:
                    targetResults[idx + 1]['urls'][str(idx_y + 1)]['sentiment'] = content_pull[idx_z]['sentiment']

    return targetResults


# -- Sentiment Analysis
def pull_sentiment(content):
    analyser = SentimentIntensityAnalyzer()
    score = analyser.polarity_scores(content)
    compound = score['compound']

    return compound


def pull_twitter_trends():
    consumer_key = ''
    consumer_secret = ''
    access_token = ''
    access_token_secret = ''

    # OAuth process, using the keys and tokens
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)

    api = tweepy.API(auth)
    trends1 = api.trends_place(23424977)
    trends = trends1[0]['trends']

    sorted_trends = sorted(trends, key=lambda i: int(i['tweet_volume'] or 0), reverse=True)
    topics = []
    for idx, trend in enumerate(sorted_trends):
        topic = trend['name'].replace('"', '')
        topic = topic.replace('#', '')
        topic = re.sub(r'([a-z](?=[A-Z])|[A-Z](?=[A-Z][a-z]))', r'\1 ', topic)

        if idx < 15:
            topics.append(topic)

    return topics


def pull_google_trends():
    # -- init Google Trends API connection
    pytrends = TrendReq(hl='en-US', tz=360)

    # -- pulling Google Trends data
    trends = pytrends.trending_searches(pn='united_states')
    trendValues = trends[0].tolist()

    # res = {i+1: trendValues[i] for i in range(len(trendValues))}
    res = {i + 1: trendValues[i] for i in range(10)}

    return res


def get_everything(keyword, fromdate, currentdate):
    newsapi = NewsApiClient(api_key='')
    articles = newsapi.get_everything(q=keyword,
                                      from_param=fromdate,
                                      to=currentdate,
                                      language='en',
                                      sort_by='relevancy',
                                      page_size=20)

    content = []
    if articles['totalResults'] > 20:
        for article in articles['articles']:
            detail = {'title': article['title'], 'url': article['url'], 'source': article['source']['name']}
            content.append(detail)

    return content


def full_build(site, dump=False):
    target = build_json(site)
    # Currently not working for Twitter pulls
    target = topic_avg_sent(target)

    today = datetime.today().strftime('%Y-%m-%d')
    for each in target:
        target[each]['date'] = today

    if dump:
        with open('testresults.json', 'w') as fp:
            json.dump(target, fp)

    return target


def init_dynamodb():
    # Get the service resource.
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    topics = dynamodb.Table('')
    sources = dynamodb.Table('')

    return [topics, sources]


def batch_load_dynamodb(tables, loaddict):
    topicsTable = tables[0];
    sourcesTable = tables[1];

    sourcesIdx = 1;
    sources = {}
    for idx in loaddict:
        if len(loaddict[idx]['urls']) > 0:
            loaddict[idx]['id'] = loaddict[idx]['date'] + "_" + str(idx)
            for url in loaddict[idx]['urls']:
                if 'sentiment' in loaddict[idx]['urls'][url]:
                    loaddict[idx]['urls'][url]['sentiment'] = str(loaddict[idx]['urls'][url]['sentiment'])
                    sources[sourcesIdx] = {}
                    sources[sourcesIdx]['id'] = loaddict[idx]['id'] + "_" + url
                    sources[sourcesIdx]['topic'] = loaddict[idx]['id']
                    sources[sourcesIdx]['source'] = loaddict[idx]['urls'][url]['source']
                    sources[sourcesIdx]['title'] = loaddict[idx]['urls'][url]['title']
                    sources[sourcesIdx]['url'] = loaddict[idx]['urls'][url]['url']
                    sources[sourcesIdx]['sentiment'] = loaddict[idx]['urls'][url]['sentiment']
                    sourcesIdx += 1

    with topicsTable.batch_writer() as batch:
        for each in loaddict:
            if len(loaddict[each]['urls']) > 0:
                loaddict[each].pop('urls', None)
                batch.put_item(
                    Item=loaddict[each]
                )

    with sourcesTable.batch_writer() as batch:
        for each in sources:
            batch.put_item(
                Item=sources[each]
            )


# Lambda function initiation for serverless
def scrape(event, context):
    dict_to_load = full_build('Google', dump=False)
    print("Dictionary loaded successfully")

    batch_load_dynamodb(tables=init_dynamodb(), loaddict=dict_to_load)

    response = "Content updated successfully"

    return response