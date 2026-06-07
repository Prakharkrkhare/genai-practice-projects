from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client=OpenAI()

def generate_subject_line(product_name:str) ->str:
  """
  Called by the RQ worker for each product.
  Sends a prompt to gpt-4o-mini and returns the subject line string.
  """

  response=client.chat.completions.create(
    model="gpt-4o-mini", # fast and cheap; perfect for short text generation
    messages=[
      {
      "role":"system",
      "content":("You are email emarketing expert."
                 "When given a product name, respond with exaclty ONE "
                 "catchy, compelling email subject line. No explaination,"
                 "no punctuation around it, just the subject line itself."
                 )
              },
      {
      "role":"user",
      "content":f"Product:{product_name}"# the only variable part
              }
    ],
    max_tokens=60,# subject lines are short; this keeps cost low
    temperature=0.8,# slight randomness = more creative outputs

  )
  return response.choices[0].message.content.strip()#strips whitespace from the start and end of the string, white space includes spaces, tabs, and newlines. This ensures the returned subject line is clean and ready to use without any extra spaces.