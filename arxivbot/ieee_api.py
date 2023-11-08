"""Untested. Still waiting for API key approval at time of writing. Apparently this is quite slow..."""

import os

import requests
from dotenv import load_dotenv


def get_ieee_paper_data(article_number):
    load_dotenv("credentials.env")
    base_url = "https://ieeexploreapi.ieee.org/api/v1/search/articles"
    params = {"apikey": os.environ["IEEE_API_KEY"], "article_number": article_number}

    response = requests.get(base_url, params=params)

    if response.status_code != 200:
        return f"Error: Unable to access the API. Status code: {response.status_code}"

    paper_data = response.json()
    return paper_data


article_number = "9381661"
paper_data = get_ieee_paper_data(article_number)
print(paper_data)
