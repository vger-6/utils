import argparse
import pandas as pd

def print_csv(file_path, separator):
	try:
		df = pd.read_csv(file_path, sep=separator)
		with pd.option_context('display.max_rows', None,
                       'display.max_columns', None):
			print(df)
	except FileNotFoundError:
		print(f"The file {file_path} does not exist.")
	except Exception as e:
		print(f"An error occurred: {e}")

def main():
	parser = argparse.ArgumentParser(description='Print a CSV file.')
	parser.add_argument('file_path', type=str, help='Path to the CSV file')
	parser.add_argument('-s', '--separator', type=str, default=',', help='Separator used in the CSV file (default: ;)')
    
	args = parser.parse_args()
    
	print_csv(args.file_path, args.separator)

if __name__ == "__main__":
	main()

