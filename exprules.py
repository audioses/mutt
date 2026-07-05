# exclusion_manager.py


class ExclusionManager:
    def __init__(self):
        self.sectional_rules = [] # Stores rules like [{'start_idx': int, 'end_idx': int}]

    def add_rule(self, start_idx, end_idx=-1):
        """Adds a new sectional exclusion rule based on entry indices."""
        if start_idx == -1:
            raise ValueError("Start index cannot be -1.")
        self.sectional_rules.append({'start_idx': start_idx, 'end_idx': end_idx})

    def remove_rule(self, index):
        """Removes a sectional exclusion rule by its index in the rules list."""
        if 0 <= index < len(self.sectional_rules):
            del self.sectional_rules[index]
            return True
        return False

    def get_rules_for_display(self, all_entries_msgids):
        """Returns a list of human-readable rule strings for display in a ListBox, using msgids from the full list."""
        display_rules = []
        for rule in self.sectional_rules:
            start_text = all_entries_msgids[rule['start_idx']]
            
            end_text_display = ""
            if rule['end_idx'] != -1:
                end_text_display = f"\"{all_entries_msgids[rule['end_idx']][:30]}...\""
            else:
                end_text_display = "[End of document]"

            display_rules.append(f"FROM: \"{start_text[:30]}...\" TO: {end_text_display}")
        return display_rules
        
    def set_rules(self, rules_list):
        """Sets the internal list of rules (e.g., when loading from a project file)."""
        self.sectional_rules = rules_list

    def get_rules(self):
        """Returns the raw list of sectional rules."""
        return self.sectional_rules
        
    def export_rules_to_file(self, file_path):
        """Exports the current sectional rules to a JSON file."""
        import json
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.sectional_rules, f, indent=4)
            return True, "Exclusion rules exported successfully."
        except Exception as e:
            return False, f"Failed to export rules: {e}"

    def to_json(self):
        """Serializes the sectional rules to a JSON-compatible format."""
        return self.sectional_rules

    @classmethod
    def from_json(cls, json_data):
        """
        Creates an ExclusionManager instance from JSON data.
        Assumes json_data is a list of dictionaries, each with 'start_idx' and 'end_idx' keys.
        """
        manager = cls()
        if isinstance(json_data, list):
            manager.set_rules(json_data)
        return manager

    def apply_sectional_rules(self, all_entries):
        """
        Applies sectional exclusion rules to a list of entries based on their indices.
        Returns a new list with excluded entries removed.
        """
        if not isinstance(all_entries, list):
            raise TypeError("all_entries must be a list.")

        if not self.sectional_rules:
            return all_entries[:] # No rules, return a copy of all entries

        entries_to_exclude_indices = set()
        
        # Iterate through all rules and mark entries for exclusion by index
        for rule in self.sectional_rules:
            start_idx = rule['start_idx']
            end_idx = rule.get('end_idx', -1) # -1 means till end of document

            # Determine the actual end index for the range
            actual_end_idx = len(all_entries) - 1 if end_idx == -1 else end_idx

            # Ensure valid range
            if start_idx < 0 or start_idx >= len(all_entries):
                continue # Invalid start index
            if actual_end_idx < start_idx or actual_end_idx >= len(all_entries):
                actual_end_idx = len(all_entries) - 1 # Adjust invalid end index to end of document

            for i in range(start_idx, actual_end_idx + 1):
                entries_to_exclude_indices.add(i)
        
        # Build a new list excluding the marked entries
        filtered_entries = [entry for i, entry in enumerate(all_entries) if i not in entries_to_exclude_indices]
        
        return filtered_entries

    def is_excluded_by_index(self, original_idx_to_check, all_entries_msgids):
        """
        Checks if a given entry (by its original index) is part of an excluded section.
        This method requires the context of the full list length.
        """
        if not self.sectional_rules:
            return False # No rules, nothing is excluded

        for rule in self.sectional_rules:
            start_idx = rule['start_idx']
            end_idx = rule.get('end_idx', -1) # -1 means till end of document

            actual_end_idx = len(all_entries_msgids) - 1 if end_idx == -1 else end_idx

            if start_idx <= original_idx_to_check <= actual_end_idx:
                return True
        return False
