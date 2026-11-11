> ## Documentation Index
> Fetch the complete documentation index at: https://platform.kimi.ai/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Best Practices for Prompts

> Write more reliable and controllable Kimi system and user prompts with clear instructions, examples, roles, and output constraints.

> Best Practices for System Prompts: A system prompt refers to the initial input or instruction that a model receives before generating text or responding. This prompt is crucial for the model's operation [link](https://kimi.moonshot.cn/share/col3fn2lnl95v16j0g2g).

## Write Clear Instructions

* Why is it necessary to provide clear instructions to the model?

> The model can't read your mind. If the output is too long, you can ask the model to respond briefly. If the output is too simple, you can request expert-level writing. If you don't like the format of the output, show the model the format you'd like to see. The less the model has to guess about your needs, the more likely you are to get satisfactory results.

### Including More Details in Your Request Can Yield More Relevant Responses

> To obtain highly relevant output, ensure that your input request includes all important details and context.

| General Request | Better Request |
| - | - |
| How to add numbers in Excel? | How do I sum a row of numbers in an Excel table? I want to automatically sum each row in the entire table and place all the totals in the rightmost column named "Total." |
| Work report summary | Summarize my work records from 2023 in a paragraph of no more than 500 words. List the highlights of each month in sequence and provide a summary of the entire year. |

### Requesting the Model to Assume a Role Can Yield More Accurate Output

> Add a specified role for the model to use in its response in the 'messages' field of the API request.

```json theme={null}
{
  "messages": [
    {"role": "system", "content": "You are Kimi, an artificial intelligence assistant provided by Moonshot AI. You are more proficient in Chinese and English conversations. You provide users with safe, helpful, and accurate answers. At the same time, you will refuse to answer any questions involving terrorism, racism, or explicit violence. Moonshot AI is a proper noun and should not be translated into other languages."},
    {"role": "user", "content": "Hello, my name is Li Lei. What is 1+1?"}
  ]
}
```

### Using Delimiters in Your Request to Clearly Distinguish Different Parts of the Input

> For example, using triple quotes/XML tags/section headings as delimiters can help distinguish text parts that require different processing.

```json theme={null}
{
  "messages": [
    {"role": "system", "content": "You will receive two articles of the same category, separated by XML tags. First, summarize the arguments of each article, then point out which article presents a better argument and explain why."},
    {"role": "user", "content": "<article>Insert article here</article><article>Insert article here</article>"}
  ]
}
```

```json theme={null}
{
  "messages": [
    {"role": "system", "content": "You will receive an abstract and the title of a paper. The title should give readers a clear idea of the paper's topic and also be eye-catching. If the title you receive does not meet these standards, please suggest five alternative options."},
    {"role": "user", "content": "Abstract: Insert abstract here.\n\nTitle: Insert title here"}
  ]
}
```

### Clearly Define the Steps Needed to Complete the Task

> It is advisable to outline a series of steps for the task. Writing these steps explicitly makes it easier for the model to follow and produces better output.

```json theme={null}
{
  "messages": [
    {"role": "system", "content": "Respond to user input using the following steps.\nStep one: The user will provide text enclosed in triple quotes. Summarize this text into one sentence with the prefix “Summary: ”.\nStep two: Translate the summary from step one into English and add the prefix \"Translation: \"."},
    {"role": "user", "content": "\"\"\"Insert text here\"\"\""}
  ]
}
```

### Provide Examples of Desired Output to the Model

> Providing examples of general guidance is usually more efficient for the model's output than showing all permutations of the task. For instance, if you intend to have the model replicate a style that is difficult to describe explicitly in response to user queries, this is known as a "few-shot" prompt.

```json theme={null}
{
  "messages": [
    {"role": "system", "content": "Respond in a consistent style"},
    {"role": "user", "content": "Insert text here"}
  ]
}
```

### Specify the Desired Length of the Model's Output

> You can request the model to generate output of a specific target length. The target output length can be specified in terms of words, sentences, paragraphs, bullet points, etc. However, note that instructing the model to generate a specific number of words is not highly precise. The model is better at generating output of a specific number of paragraphs or bullet points.

```json theme={null}
{
  "messages": [
    {"role": "user", "content": "Summarize the text within the triple quotes in two sentences, within 50 words. \"\"\"Insert text here\"\"\""}
  ]
}
```

## Provide Reference Text

### Guide the Model to Use Reference Text to Answer Questions

> If you can provide a model with credible information related to the current query, you can guide the model to use the provided information to answer the question.

```json theme={null}
{
  "messages": [
    {"role": "system", "content": "Answer the question using the provided article (enclosed in triple quotes). If the answer is not found in the article, write \"I can't find the answer.\""},
    {"role": "user", "content": "<Insert article, each article enclosed in triple quotes>"}
  ]
}
```

## Break Down Complex Tasks

### Categorize to Identify Instructions Relevant to User Queries

> For tasks that require a large set of independent instructions to handle different scenarios, categorizing the query type and using this categorization to clarify which instructions are needed may aid the output.

Based on the classification of the customer query, a set of more specific instructions can be provided to the model to help it handle subsequent steps. For example, assume the customer needs help with “troubleshooting.”

```json theme={null}
{
  "messages": [
    {"role": "system", "content": "You will receive a customer service inquiry that requires technical support. You can assist the user in the following ways:\n\n-Ask them to check if *** is configured.\nIf all *** are configured but the problem persists, ask for the device model they are using\n-Now you need to tell them how to restart the device:\n=If the device model is A, perform ***.\n-If the device model is B, suggest they perform ***."}
  ]
}
```

### For Long-Running Dialog Applications, Summarize or Filter Previous Conversations

> Since the model has a fixed context length, the conversation between the user and the model assistant cannot continue indefinitely.

One solution to this issue is to summarize the first few rounds of the conversation. Once the input size reaches a predetermined threshold, a query is triggered to summarize the previous part of the conversation, and the summary of the previous conversation can also be included as part of the system message. Alternatively, previous conversations throughout the entire chat process can be summarized asynchronously.

### Chunk and Recursively Build a Complete Summary for Long Documents

> To summarize the content of a book, we can use a series of queries to summarize each chapter of the document. Partial summaries can be aggregated and summarized to produce a summary of summaries. This process can be recursively repeated until the entire book is summarized. If understanding later parts requires reference to earlier chapters, then when summarizing a specific point in the book, include summaries of the chapters preceding that point.
