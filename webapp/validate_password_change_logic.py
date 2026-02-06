#!/usr/bin/env python3
"""
Standalone Password Change Logic Validator

This script validates the password change workflow for commander credentials:
1. Get current password from Bitwarden
2. Test current password on up to 3 random commanders
3. If any test fails, stop and report error
4. If all tests pass, change password on all commanders
5. Update password in Bitwarden

This script can be run independently to test the logic before applying
to the main application.
"""

import random
import sqlite3
import sys
from typing import List, Dict, Tuple
import os

# Add lib directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))

from lib.bitwarden_api_client import BitwardenService
from lib.commander_password import rotate_password_on_commander, get_token


class PasswordChangeValidator:
    """Validates and executes password changes across commanders."""

    def __init__(self, db_path: str, bitwarden_url: str = None):
        self.db_path = db_path
        self.bitwarden_url = bitwarden_url or os.getenv('BITWARDEN_SERVICE_URL', 'http://bitwarden-serve:8087')
        self.bw = None

    def get_bitwarden_service(self) -> BitwardenService:
        """Get or create Bitwarden service instance."""
        if not self.bw:
            self.bw = BitwardenService(self.bitwarden_url)
        return self.bw

    def get_enabled_commanders(self) -> List[Dict]:
        """Get all enabled commanders from database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id, ip, store_name, brand, group_name
                FROM commanders
                WHERE enabled = 1
                ORDER BY store_name
            """)
            commanders = [dict(row) for row in cursor.fetchall()]
            return commanders
        finally:
            conn.close()

    def step1_get_current_password(self, username: str) -> Tuple[bool, str, str]:
        """
        Step 1: Retrieve current password from Bitwarden.

        Args:
            username: The username to look up (e.g., admin)

        Returns:
            Tuple of (success, actual_username, password)
        """
        print(f"\n[STEP 1] Getting current password from Bitwarden for user '{username}'")

        # Map UI username to Bitwarden item name
        item_name_map = {
            'admin': 'Commander - Admin',
            # Add additional Bitwarden item mappings here as needed
        }

        item_name = item_name_map.get(username)
        if not item_name:
            print(f"  ❌ Unknown username: {username}")
            return False, None, None

        try:
            bw = self.get_bitwarden_service()
            actual_username, password = bw.get_credentials(item_name)

            if not password:
                print(f"  ❌ Could not retrieve password from Bitwarden item '{item_name}'")
                return False, None, None

            print(f"  ✅ Retrieved credentials: username='{actual_username}', password={'*' * len(password)}")
            return True, actual_username, password

        except Exception as e:
            print(f"  ❌ Error connecting to Bitwarden: {e}")
            return False, None, None

    def step2_test_current_password(
        self,
        commanders: List[Dict],
        actual_username: str,
        current_password: str,
        test_count: int = 3
    ) -> Tuple[bool, List[Dict]]:
        """
        Step 2: Test current password on random sample of commanders.

        Args:
            commanders: List of all enabled commanders
            actual_username: The actual username from Bitwarden
            current_password: Current password to test
            test_count: Number of random commanders to test (default 3)

        Returns:
            Tuple of (all_tests_passed, test_results)
        """
        print(f"\n[STEP 2] Testing current password on up to {test_count} random commanders")

        if not commanders:
            print("  ❌ No enabled commanders to test")
            return False, []

        # Select random sample (or all if less than test_count)
        test_commanders = random.sample(commanders, min(test_count, len(commanders)))

        test_results = []
        all_passed = True

        for idx, commander in enumerate(test_commanders, 1):
            print(f"\n  Testing {idx}/{len(test_commanders)}: {commander['store_name']} ({commander['ip']})")

            try:
                # Attempt to get token with current password
                token = get_token(
                    ip=commander['ip'],
                    username=actual_username,
                    password=current_password,
                    timeout=30
                )

                if token:
                    print(f"    ✅ Authentication successful")
                    test_results.append({
                        'commander': commander,
                        'success': True,
                        'message': 'Authentication successful'
                    })
                else:
                    print(f"    ❌ Authentication FAILED - current password does not work")
                    test_results.append({
                        'commander': commander,
                        'success': False,
                        'message': 'Authentication failed with current password'
                    })
                    all_passed = False

            except Exception as e:
                print(f"    ❌ Error during test: {e}")
                test_results.append({
                    'commander': commander,
                    'success': False,
                    'message': f'Exception: {str(e)}'
                })
                all_passed = False

        if all_passed:
            print(f"\n  ✅ All {len(test_commanders)} test(s) passed - current password is valid")
        else:
            print(f"\n  ❌ One or more tests FAILED - cannot proceed with password change")

        return all_passed, test_results

    def step3_validate_new_password(self, new_password: str) -> Tuple[bool, str]:
        """
        Step 3: Validate new password meets requirements.

        Args:
            new_password: The new password to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        print(f"\n[STEP 3] Validating new password")

        if not new_password:
            return False, "Password cannot be empty"

        if len(new_password) < 7:
            return False, "Password must be at least 7 characters"

        if len(new_password) > 10:
            return False, "Password must be no more than 10 characters"

        has_letter = any(c.isalpha() for c in new_password)
        has_digit = any(c.isdigit() for c in new_password)

        if not has_letter:
            return False, "Password must contain at least one letter"

        if not has_digit:
            return False, "Password must contain at least one digit"

        print(f"  ✅ New password is valid ({len(new_password)} chars, has letters and digits)")
        return True, None

    def step4_change_passwords(
        self,
        commanders: List[Dict],
        actual_username: str,
        current_password: str,
        new_password: str
    ) -> Tuple[int, int, List[Dict]]:
        """
        Step 4: Change password on all enabled commanders.

        Args:
            commanders: List of all enabled commanders
            actual_username: The actual username from Bitwarden
            current_password: Current password
            new_password: New password to set

        Returns:
            Tuple of (succeeded_count, failed_count, detailed_results)
        """
        print(f"\n[STEP 4] Changing password on all {len(commanders)} enabled commanders")

        results = []
        succeeded = 0
        failed = 0

        for idx, commander in enumerate(commanders, 1):
            print(f"\n  {idx}/{len(commanders)}: {commander['store_name']} ({commander['ip']})")

            try:
                result = rotate_password_on_commander(
                    ip=commander['ip'],
                    username=actual_username,
                    current_password=current_password,
                    new_password=new_password,
                    timeout=30
                )

                if result['success']:
                    print(f"    ✅ {result['message']}")
                    succeeded += 1
                else:
                    print(f"    ❌ {result['message']}")
                    failed += 1

                results.append({
                    'ip': commander['ip'],
                    'store_name': commander['store_name'],
                    'success': result['success'],
                    'message': result['message']
                })

            except Exception as e:
                print(f"    ❌ Exception: {e}")
                failed += 1
                results.append({
                    'ip': commander['ip'],
                    'store_name': commander['store_name'],
                    'success': False,
                    'message': f'Exception: {str(e)}'
                })

        print(f"\n  Results: {succeeded} succeeded, {failed} failed out of {len(commanders)} total")
        return succeeded, failed, results

    def step5_update_bitwarden(self, username: str, new_password: str) -> bool:
        """
        Step 5: Update password in Bitwarden vault.

        Args:
            username: The username to update
            new_password: The new password to store

        Returns:
            True if update succeeded, False otherwise
        """
        print(f"\n[STEP 5] Updating password in Bitwarden for user '{username}'")

        item_name_map = {
            'admin': 'Commander - Admin',
            # Add additional Bitwarden item mappings here as needed
        }

        item_name = item_name_map.get(username)
        if not item_name:
            print(f"  ❌ Unknown username: {username}")
            return False

        try:
            bw = self.get_bitwarden_service()
            if bw.update_password(item_name, new_password):
                print(f"  ✅ Password updated in Bitwarden item '{item_name}'")
                return True
            else:
                print(f"  ❌ Failed to update password in Bitwarden")
                return False

        except Exception as e:
            print(f"  ❌ Error updating Bitwarden: {e}")
            return False

    def execute_password_change(
        self,
        username: str,
        new_password: str,
        dry_run: bool = False
    ) -> Dict:
        """
        Execute complete password change workflow.

        Args:
            username: Username to change password for
            new_password: New password to set
            dry_run: If True, only test current password but don't change anything

        Returns:
            Dict with results and status
        """
        print("=" * 80)
        print(f"PASSWORD CHANGE WORKFLOW - User: {username}")
        print(f"Mode: {'DRY RUN (testing only)' if dry_run else 'LIVE (will change passwords)'}")
        print("=" * 80)

        # Step 1: Get current password from Bitwarden
        success, actual_username, current_password = self.step1_get_current_password(username)
        if not success:
            return {
                'success': False,
                'step': 1,
                'message': 'Failed to retrieve current password from Bitwarden'
            }

        # Get all enabled commanders
        commanders = self.get_enabled_commanders()
        if not commanders:
            return {
                'success': False,
                'step': 1,
                'message': 'No enabled commanders found in database'
            }

        print(f"\nFound {len(commanders)} enabled commanders")

        # Step 2: Test current password on random sample
        tests_passed, test_results = self.step2_test_current_password(
            commanders,
            actual_username,
            current_password,
            test_count=min(3, len(commanders))
        )

        if not tests_passed:
            return {
                'success': False,
                'step': 2,
                'message': 'Current password validation failed on one or more commanders',
                'test_results': test_results
            }

        # If dry run, stop here
        if dry_run:
            print("\n" + "=" * 80)
            print("DRY RUN COMPLETE - Current password is valid, but no changes were made")
            print("=" * 80)
            return {
                'success': True,
                'dry_run': True,
                'message': 'Current password validated successfully (dry run)',
                'test_results': test_results
            }

        # Step 3: Validate new password
        valid, error_msg = self.step3_validate_new_password(new_password)
        if not valid:
            return {
                'success': False,
                'step': 3,
                'message': f'New password validation failed: {error_msg}'
            }

        # Step 4: Change passwords on all commanders
        succeeded, failed, change_results = self.step4_change_passwords(
            commanders,
            actual_username,
            current_password,
            new_password
        )

        # Only update Bitwarden if ALL commanders succeeded
        bitwarden_updated = False
        if succeeded > 0 and failed == 0:
            # Step 5: Update Bitwarden
            bitwarden_updated = self.step5_update_bitwarden(username, new_password)
        else:
            print(f"\n⚠️  Skipping Bitwarden update because {failed} commander(s) failed")

        print("\n" + "=" * 80)
        print("PASSWORD CHANGE WORKFLOW COMPLETE")
        print("=" * 80)

        return {
            'success': succeeded > 0 and failed == 0,
            'succeeded': succeeded,
            'failed': failed,
            'total': len(commanders),
            'bitwarden_updated': bitwarden_updated,
            'change_results': change_results,
            'message': f'Changed {succeeded}/{len(commanders)} commanders, Bitwarden updated: {bitwarden_updated}'
        }


def main():
    """Main entry point for testing."""
    import argparse

    parser = argparse.ArgumentParser(description='Validate password change logic')
    parser.add_argument('--username', required=True,
                       choices=['admin'],
                       help='Username to change password for')
    parser.add_argument('--new-password', help='New password to set')
    parser.add_argument('--dry-run', action='store_true',
                       help='Only test current password, do not change')
    parser.add_argument('--db-path',
                       default='/app/data/database/posproctor.db',
                       help='Path to SQLite database')

    args = parser.parse_args()

    # Validate arguments
    if not args.dry_run and not args.new_password:
        print("Error: --new-password is required unless using --dry-run")
        sys.exit(1)

    # Execute workflow
    validator = PasswordChangeValidator(args.db_path)
    result = validator.execute_password_change(
        username=args.username,
        new_password=args.new_password or '',  # Empty for dry run
        dry_run=args.dry_run
    )

    # Print summary
    print("\n" + "=" * 80)
    print("RESULT SUMMARY")
    print("=" * 80)
    print(f"Success: {result['success']}")
    print(f"Message: {result['message']}")

    if not result['success']:
        sys.exit(1)


if __name__ == '__main__':
    main()
