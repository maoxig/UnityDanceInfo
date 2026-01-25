import json
import os

def sort_dances(input_file, output_file):
    # Check if the input file exists
    if not os.path.exists(input_file):
        print(f"Error: {input_file} does not exist.")
        return

    # Read the JSON data from the input file
    with open(input_file, 'r', encoding='utf-8') as file:
        dances = json.load(file)

    # Print the number of dances
    print(f"Number of dances: {len(dances)}")

    # Sort the dances by author, then by name, then by hash
    sorted_dances = dict(sorted(
        dances.items(),
        key=lambda item: (item[1]['author'], item[1]['name'], item[0])
    ))

    # Write the sorted data to the output file
    with open(output_file, 'w', encoding='utf-8') as file:
        json.dump(sorted_dances, file, indent=4, ensure_ascii=False)

    print(f"Sorted dances have been written to {output_file}")

if __name__ == "__main__":
    input_file = "DanceInfo/dances.json"
    output_file = "DanceInfo/dances.json"
    sort_dances(input_file, output_file)