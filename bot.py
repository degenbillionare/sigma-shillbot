import asyncio
import time
import aiohttp
import tempfile
import os
from twikit import Client
from PIL import Image
import random
import io

# Twitter credentials
USERNAME = os.environ.get('TWITTER_USERNAME')
EMAIL = os.environ.get('TWITTER_EMAIL')
PASSWORD = os.environ.get('TWITTER_PASSWORD')

# Tenor API key
TENOR_API_KEY = os.environ.get('TENOR_API_KEY')

# Initialize the client
client = Client('en-US')

# Rate limits
SEARCH_RATE_LIMIT = 37  # 37 searches per 15 minutes
FAVORITE_RATE_LIMIT = 375  # 375 favorites per 15 minutes
RETWEET_RATE_LIMIT = 337  # 337 retweets per 15 minutes
MEDIA_UPLOAD_RATE_LIMIT = 375  # Assuming same as favorites
TWEET_RATE_LIMIT = 300  # 300 tweets per 3 hours
RATE_LIMIT_WINDOW = 15 * 60  # 15 minutes in seconds

# Track API calls
search_calls = 0
favorite_calls = 0
retweet_calls = 0
media_upload_calls = 0
tweet_calls = 0

# Timestamps for rate limit windows
search_window_start = time.time()
favorite_window_start = time.time()
retweet_window_start = time.time()
media_upload_window_start = time.time()
tweet_window_start = time.time()

async def rate_limit_delay(action):
    global search_calls, favorite_calls, retweet_calls, media_upload_calls, tweet_calls
    global search_window_start, favorite_window_start, retweet_window_start, media_upload_window_start, tweet_window_start
    
    current_time = time.time()

    if action == 'search' and search_calls >= SEARCH_RATE_LIMIT:
        await reset_window(current_time, 'search')
    elif action == 'favorite' and favorite_calls >= FAVORITE_RATE_LIMIT:
        await reset_window(current_time, 'favorite')
    elif action == 'retweet' and retweet_calls >= RETWEET_RATE_LIMIT:
        await reset_window(current_time, 'retweet')
    elif action == 'media_upload' and media_upload_calls >= MEDIA_UPLOAD_RATE_LIMIT:
        await reset_window(current_time, 'media_upload')
    elif action == 'tweet' and tweet_calls >= TWEET_RATE_LIMIT:
        await reset_window(current_time, 'tweet')

async def reset_window(current_time, action):
    global search_window_start, favorite_window_start, retweet_window_start, media_upload_window_start, tweet_window_start
    global search_calls, favorite_calls, retweet_calls, media_upload_calls, tweet_calls

    window_start = globals()[f"{action}_window_start"]
    window_elapsed = current_time - window_start
    if window_elapsed < RATE_LIMIT_WINDOW:
        await asyncio.sleep(RATE_LIMIT_WINDOW - window_elapsed)
    
    globals()[f"{action}_calls"] = 0
    globals()[f"{action}_window_start"] = time.time()

async def compress_gif(file_path, max_size_bytes=5000000):  # Slightly under 5MB to be safe
    with Image.open(file_path) as img:
        frames = []
        for frame in range(img.n_frames):
            img.seek(frame)
            frames.append(img.copy())
        
        output = io.BytesIO()
        frames[0].save(output, format='GIF', save_all=True, append_images=frames[1:], loop=0, optimize=True)
        
        while output.tell() > max_size_bytes:
            output = io.BytesIO()
            frames = [frame.resize((int(frame.width * 0.9), int(frame.height * 0.9))) for frame in frames]
            frames[0].save(output, format='GIF', save_all=True, append_images=frames[1:], loop=0, optimize=True)
        
        with open(file_path, 'wb') as f:
            f.write(output.getvalue())

async def download_gif(session, url, file_path):
    async with session.get(url) as response:
        if response.status == 200:
            with open(file_path, 'wb') as f:
                f.write(await response.read())
            await compress_gif(file_path)

async def get_random_sigma_gif(session):
    url = "https://tenor.googleapis.com/v2/search"
    params = {
        "q": "sigma",
        "key": TENOR_API_KEY,
        "client_key": "my_test_app",
        "limit": 50  # Request 50 results instead of 1
    }
    async with session.get(url, params=params) as response:
        data = await response.json()
        if "results" in data and len(data["results"]) > 0:
            # Randomly select one GIF from the results
            random_gif = random.choice(data["results"])
            return random_gif["media_formats"]["gif"]["url"]
    return None

async def main():
    global search_calls, favorite_calls, retweet_calls, media_upload_calls, tweet_calls

    # Log in to your Twitter account
    await client.login(
        auth_info_1=USERNAME,
        auth_info_2=EMAIL,
        password=PASSWORD
    )

    async with aiohttp.ClientSession() as session:
        while True:  # Continuous loop
            try:
                # Search for the latest tweets mentioning "$sigma"
                await rate_limit_delay('search')
                tweets = await client.search_tweet('$sigma', 'Latest')
                search_calls += 1

                # Iterate through the tweets
                for tweet in tweets:
                    try:
                        # Favorite the tweet
                        await rate_limit_delay('favorite')
                        await client.favorite_tweet(tweet.id)
                        favorite_calls += 1
                        print(f"Favorited tweet from {tweet.user.name}")

                        # Retweet the tweet
                        await rate_limit_delay('retweet')
                        await client.retweet(tweet.id)
                        retweet_calls += 1
                        print(f"Retweeted tweet from {tweet.user.name}")

                        # Get a random sigma GIF
                        gif_url = await get_random_sigma_gif(session)
                        if gif_url:
                            # Download and compress the GIF
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".gif") as temp_file:
                                await download_gif(session, gif_url, temp_file.name)
                            
                            # Upload the GIF to Twitter
                            await rate_limit_delay('media_upload')
                            try:
                                media_id = await client.upload_media(temp_file.name)
                                media_upload_calls += 1
                                
                                # Reply to the tweet with the GIF
                                await rate_limit_delay('tweet')
                                reply_tweet = await client.create_tweet(
                                    text="$SIGMA",
                                    media_ids=[media_id],
                                    reply_to=tweet.id
                                )
                                tweet_calls += 1
                                
                                print(f"Replied to tweet from {tweet.user.name} with a Sigma GIF")
                            except Exception as e:
                                if "File size exceeds" in str(e):
                                    print(f"GIF file size still too large after compression: {e}")
                                else:
                                    raise
                            finally:
                                # Clean up the temporary file
                                os.unlink(temp_file.name)
                        else:
                            print("Failed to get a Sigma GIF")

                        print(f"Processed tweet from {tweet.user.name}: {tweet.text}")
                    except Exception as e:
                        print(f"Error processing tweet: {e}")

                # Wait for a while before the next search
                await asyncio.sleep(60)  # Wait for 1 minute

            except Exception as e:
                print(f"An error occurred: {e}")
                await asyncio.sleep(300)  # Wait for 5 minutes before retrying


# Run the main function
asyncio.run(main())