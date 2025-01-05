import argparse
import os
import yaml
from dotenv import load_dotenv

from gptpdf.parse import parse_pdf

def main():
   # Load environment variables from .env file as lowest priority
   load_dotenv(override=False)  # override=False ensures .env doesn't override existing env vars

   parser = argparse.ArgumentParser(description="Parse PDF to markdown.")
   parser.add_argument("pdf_path", help="Path to the PDF file.")
   parser.add_argument("output_dir", help="Output directory.")
   parser.add_argument("--prompt-file", help="Path to a YAML file containing the prompt dictionary.")
   parser.add_argument("--api-key", help="OpenAI API key.")
   parser.add_argument("--api-key-env", default="OPENAI_API_KEY", help="Name of environment variable for API key.")
   parser.add_argument("--model", default="gpt-4", help="Language model to use.")
   parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output.")
   parser.add_argument("--base-url", help="Model provider URL", default="https://openrouter.ai/api/v1")
   parser.add_argument("--temperature", type=float, help="Model temperature (0-2)")
   parser.add_argument("--max-tokens", type=int, help="Maximum number of tokens in response")
   args = parser.parse_args()

   # Get API key with priority:
   # 1. Command line argument
   # 2. System environment variable
   # 3. Environment variable from .env
   api_key = args.api_key or os.environ.get(args.api_key_env)
   if api_key is None:
       raise ValueError(
           "API key not provided. Please either:"
           f"\n1. Use the --api-key argument"
           f"\n2. Set the {args.api_key_env} environment variable"
           f"\n3. Set {args.api_key_env} in your .env file"
       )

   # Load prompt dictionary from YAML file if provided
   if args.prompt_file:
       with open(args.prompt_file, "r") as f:
           prompt = yaml.safe_load(f)
   else:
       prompt = None

   # Call parse_pdf function
   extra_args = {}
   if args.temperature: extra_args["temperature"] = args.temperature
   if args.max_tokens: extra_args["max_tokens"] = args.max_tokens

   print (f'''..Model: {args.model}
..Provider URL: {args.base_url}
..API key symbol: {args.api_key_env}
'''
   )

   parse_pdf(
       pdf_path=args.pdf_path,
       output_dir=args.output_dir,
       prompt=prompt,
       api_key=api_key,
       model=args.model,
       verbose=args.verbose,
       base_url=args.base_url,
       **extra_args
   )

if __name__ == "__main__":
   main()