"""
Score Calculator for FPO Yearly Submissions
This module provides a scoring system for FPO yearly submissions.
"""

from typing import Optional, Dict, Literal
from .models import YearlySubmission


class FPOScoreCalculator:
    """
    Calculator for FPO yearly submission scores.
    """
    
    @staticmethod
    def get_age_based_weights(age: float) -> Dict[str, float]:
        """
        Get weight distribution based on FPO age.
        
        Args:
            age: The age of the FPO in years
            
        Returns:
            Dictionary with weights for each category:
            - governance: Governance and Management weight
            - business: Business and Operations weight
            - process: Process and Systems weight
            - financial: Financial Performance weight
            
        Age Categories and Weights:
        Below 1 Year: Governance: 40%, Business: 20%, Process: 25%, Financial: 15%
        1-3 Years: Governance: 35%, Business: 20%, Process: 25%, Financial: 20%
        3-5 Years: Governance: 30%, Business: 25%, Process: 20%, Financial: 25%
        Above 5 Years: Governance: 25%, Business: 30%, Process: 15%, Financial: 30%
        """
        if age < 1:
            return {'governance': 40.0, 'business': 20.0, 'process': 25.0, 'financial': 15.0}
        elif 1 <= age < 3:
            return {'governance': 35.0, 'business': 20.0, 'process': 25.0, 'financial': 20.0}
        elif 3 <= age < 5:
            return {'governance': 30.0, 'business': 25.0, 'process': 20.0, 'financial': 25.0}
        else:  # 5+ years
            return {'governance': 25.0, 'business': 30.0, 'process': 15.0, 'financial': 30.0}
    
    def __init__(self, yearly_submission: YearlySubmission):
        self.submission = yearly_submission
    
    def calculate_total_score(self) -> Optional[float]:
        """
        Calculate the total FPO score out of 100.
        Returns None if insufficient data is available.
        """
        try:
            # Get the age-based weights
            fpo_details = getattr(self.submission, 'fpo_details', None)
            if not fpo_details:
                return None
                
            age = fpo_details.age_of_fpo_years or 0
            weights = self.get_age_based_weights(age)
            
            # Calculate individual category scores
            governance_score = self._calculate_governance_score()
            business_score = self._calculate_business_score()
            process_score = self._calculate_process_score()
            financial_score = self._calculate_financial_score()
            
            # Apply weights and calculate total score
            total_score = (
                governance_score * (weights['governance'] / 100) +
                business_score * (weights['business'] / 100) +
                process_score * (weights['process'] / 100) +
                financial_score * (weights['financial'] / 100)
            )
            
            return round(total_score, 2)
            
        except (AttributeError, TypeError, ZeroDivisionError):
            return None

    def _calculate_governance_score(self) -> float:
        """
        Calculate governance and management score (max 20 points).
        """
        score = 0.0
        
        # 1. Promoting agency support (1 point)
        fpo_details = getattr(self.submission, 'fpo_details', None)
        if fpo_details and fpo_details.supported_by_promoting_agency:
            score += 1.0
        
        # 2. Board of Directors number scoring
        bod_score = self._calculate_bod_number_score()
        score += bod_score
        
        # 3. Board of Directors quality scoring
        bod_quality_score = self._calculate_bod_quality_score()
        score += bod_quality_score
        
        # 4. CEO quality scoring
        ceo_score = self._calculate_ceo_score()
        score += ceo_score
        
        # 5. FPO size achievement scoring
        size_achievement_score = self._calculate_size_achievement_score()
        score += size_achievement_score
        
        # 6. Second line management scoring
        second_line_score = self._calculate_second_line_score()
        score += second_line_score
        
        # 7. Minutes of meeting scoring
        minutes_score = self._calculate_minutes_score()
        score += minutes_score
        
        # 8. Active membership scoring
        active_membership_score = self._calculate_active_membership_score()
        score += active_membership_score
        
        return min(score, 20.0)  # Cap at 20 points

    def _calculate_bod_number_score(self) -> float:
        """
        Calculate score based on number of Board of Directors relative to optimal.
        Score: 3 if >= 100%, 2 if >= 75%, 1 if >= 50%, 0 if < 50%
        """
        governance = getattr(self.submission, 'governance', None)
        fpo_details = getattr(self.submission, 'fpo_details', None)
        
        if not governance or not fpo_details:
            return 0.0
            
        actual_bods = governance.num_bods or 0
        fpo_size = fpo_details.size_of_fpo_fy_23_24 or 0
        
        # Calculate optimal BOD number
        if fpo_size < 1000:
            optimal_bods = 5
        else:
            # For FPOs with more than 1000 members: 5 + 1 BOD for every additional 1000 members
            additional_members = fpo_size - 1000
            additional_bods = (additional_members + 999) // 1000  # Ceiling division
            optimal_bods = 5 + additional_bods
        
        percentage = (actual_bods / optimal_bods * 100) if optimal_bods > 0 else 0
        
        if percentage >= 100:
            return 3.0
        elif percentage >= 75:
            return 2.0
        elif percentage >= 50:
            return 1.0
        else:
            return 0.0

    def _calculate_bod_quality_score(self) -> float:
        """
        Calculate BOD quality score based on experience (max 4 points per director).
        """
        board_directors = getattr(self.submission, 'board_directors', None)
        if not board_directors:
            return 0.0
            
        total_score = 0.0
        count = 0
        
        for director in board_directors.all():
            experience = director.total_years_of_experience or 0
            director_score = 0.0
            
            # Experience-based scoring
            if experience >= 12:
                director_score = 4.0
            elif experience >= 10:
                director_score = 3.0
            elif experience >= 8:
                director_score = 2.0
            elif experience >= 5:
                director_score = 1.0
            
            # Apply 0.5 multiplier if no relevant experience
            if (not director.type_of_experience or
                director.type_of_experience == 'any_other'):
                director_score *= 0.5
            
            total_score += director_score
            count += 1
        
        # Return average score per director (max 4 points)
        return min(total_score / max(count, 1), 4.0) if count > 0 else 0.0

    def _calculate_ceo_score(self) -> float:
        """
        Calculate CEO quality score based on experience (max 4 points).
        """
        ceo_profile = getattr(self.submission, 'ceo_profile', None)
        if not ceo_profile:
            return 0.0
            
        experience = ceo_profile.total_years_of_experience or 0
        
        if experience >= 12:
            return 4.0
        elif experience >= 10:
            return 3.0
        elif experience >= 8:
            return 2.0
        elif experience >= 5:
            return 1.0
        else:
            return 0.0

    def _calculate_size_achievement_score(self) -> float:
        """
        Calculate FPO size achievement score.
        Score: 3 if >= 75%, 2 if >= 50%, 1 if >= 25%, 0 if < 25%
        """
        fpo_details = getattr(self.submission, 'fpo_details', None)
        if not fpo_details:
            return 0.0
            
        actual_size = fpo_details.size_of_fpo_fy_23_24 or 0
        target_size = fpo_details.target_size_of_fpo or 0
        
        if target_size > 0:
            achievement = (actual_size / target_size) * 100
            
            if achievement >= 75:
                return 3.0
            elif achievement >= 50:
                return 2.0
            elif achievement >= 25:
                return 1.0
        
        return 0.0

    def _calculate_second_line_score(self) -> float:
        """
        Calculate second line management score.
        """
        governance = getattr(self.submission, 'governance', None)
        if not governance or not governance.second_line_management:
            return 0.0
            
        second_line = governance.second_line_management
        
        if second_line == 'ceo_accounts_two_managers':
            return 4.0
        elif second_line == 'ceo_accounts_one_manager':
            return 3.0
        elif second_line == 'ceo_with_accounts':
            return 2.0
        elif second_line == 'only_ceo':
            return 1.0
        elif second_line == 'no_ceo':
            return 0.0
        else:
            return 0.0

    def _calculate_minutes_score(self) -> float:
        """
        Calculate minutes of meeting score.
        """
        governance = getattr(self.submission, 'governance', None)
        if not governance or not governance.minutes_maintenance:
            return 0.0
            
        minutes = governance.minutes_maintenance
        
        if minutes == 'detailed_compliant':
            return 3.0
        elif minutes == 'detailed_not_updated':
            return 2.0
        elif minutes == 'sketchy_quality':
            return 1.0
        elif minutes == 'not_maintained':
            return 0.0
        else:
            return 0.0

    def _calculate_active_membership_score(self) -> float:
        """
        Calculate active membership score.
        Score: 3 if >= 75%, 2 if >= 50%, 1 if >= 25%, 0 if < 25%
        """
        fpo_details = getattr(self.submission, 'fpo_details', None)
        if not fpo_details:
            return 0.0
            
        farmers_transacted = fpo_details.farmers_transacted or 0
        size = fpo_details.size_of_fpo_fy_23_24 or 0
        
        if size > 0:
            active_percentage = (farmers_transacted / size) * 100
            
            if active_percentage >= 75:
                return 3.0
            elif active_percentage >= 50:
                return 2.0
            elif active_percentage >= 25:
                return 1.0
        
        return 0.0

    def _calculate_business_score(self) -> float:
        """
        Calculate business and operations score (placeholder).
        TODO: Implement business operations scoring logic
        """
        return 10.0

    def _calculate_process_score(self) -> float:
        """
        Calculate process and systems score based on 7 indicators (max 19 points total).
        
        Indicators:
        1. Accounts and MIS (max 3 points)
        2. Insurance of stock (max 3 points)
        3. Credit record (max 3 points)
        4. Statutory fillings (max 3 points)
        5. Books and records up to date (max 3 points)
        6. Reconciliation of stocks (max 3 points)
        7. Penalties levied (max 1 point)
        """
        try:
            processes_systems = getattr(self.submission, 'processes_systems', None)
            
            if not processes_systems:
                return 0.0
                
            score = 0.0
            
            # 1. Accounts and MIS (max 3 points)
            if processes_systems.accounts_and_mis:
                if processes_systems.accounts_and_mis == 'software_digital':
                    score += 3.0  # Software for managing accounts & digitalization of MIS
                elif processes_systems.accounts_and_mis == 'tally_no_digital':
                    score += 2.0  # Accounting managed by tally, but no digitalization of other records
                elif processes_systems.accounts_and_mis == 'ms_office_tools':
                    score += 1.0  # Accounting managed by MS Office tools but not software packages
                elif processes_systems.accounts_and_mis == 'no_mis':
                    score += 0.0  # No MIS present, accounting done manually
            
            # 2. Insurance of stock (max 3 points)
            if processes_systems.insurance_of_stock:
                if processes_systems.insurance_of_stock == '100_fire_theft':
                    score += 3.0  # 100% stock insured against fire & theft
                elif processes_systems.insurance_of_stock == '50_fire_theft':
                    score += 2.0  # 50% of stock insured against fire & theft
                elif processes_systems.insurance_of_stock == 'less_than_50_fire':
                    score += 1.0  # Less than 50% or insurance cover is either for fire or theft only
                elif processes_systems.insurance_of_stock == 'no_insurance':
                    score += 0.0  # No insurance coverage
            
            # 3. Credit record of FPO (max 3 points)
            if processes_systems.credit_record_of_fpo:
                if processes_systems.credit_record_of_fpo == 'no_delays':
                    score += 3.0  # No record of delays/defaults
                elif processes_systems.credit_record_of_fpo == 'one_delay':
                    score += 2.0  # One record of delays/defaults in last 3 financial years
                elif processes_systems.credit_record_of_fpo == 'multiple_delays':
                    score += 1.0  # More than one record of delays/defaults in last 3 financial years
                elif processes_systems.credit_record_of_fpo == 'no_credit_history':
                    score += 0.0  # No credit history
            
            # 4. Statutory fillings (max 3 points)
            if processes_systems.statutory_fillings:
                if processes_systems.statutory_fillings == 'no_delays':
                    score += 3.0  # No delays
                elif processes_systems.statutory_fillings == 'few_delays_filled':
                    score += 2.0  # Few delays (<3) over past 12 months but filled as on date
                elif processes_systems.statutory_fillings == 'multiple_delays_filled':
                    score += 1.0  # Multiple delays (>5) over past 12 months but filled as on date
                elif processes_systems.statutory_fillings == 'delays_not_filled':
                    score += 0.0  # Any delays in past 12 months not yet filled
            
            # 5. Books and records up to date (max 3 points)
            if processes_systems.books_and_records_up_to_date:
                if processes_systems.books_and_records_up_to_date == 'current':
                    score += 3.0  # Current
                elif processes_systems.books_and_records_up_to_date == 'lag_2_3_days':
                    score += 2.0  # Updated with a lag of 2-3 days
                elif processes_systems.books_and_records_up_to_date == 'weekly_updated':
                    score += 1.0  # Updated on weekly basis
                elif processes_systems.books_and_records_up_to_date == 'processes_systems':
                    score += 0.0  # Updated on a monthly or more basis
            
            # 6. Reconciliation of stocks (max 3 points)
            if processes_systems.reconciliation_of_stocks:
                if processes_systems.reconciliation_of_stocks == 'every_15_days':
                    score += 3.0  # At least every 15 days
                elif processes_systems.reconciliation_of_stocks == 'monthly':
                    score += 2.0  # Monthly
                elif processes_systems.reconciliation_of_stocks == '2_4_times_year':
                    score += 1.0  # 2-4 times in a year
                elif processes_systems.reconciliation_of_stocks == 'absent_annual':
                    score += 0.0  # Absent or Annual
            
            # 7. Penalties levied for board meeting compliance (max 1 point)
            # Note: Based on the user's table, this should be 1 point if no penalties, not 3
            if processes_systems.penalties_levied_board_meeting is False:
                score += 1.0  # No penalties levied in financial year 2022-23
            # If penalties_levied_board_meeting is True, no points are added (penalties were levied)
            
            return min(score, 20.0)  # Cap at 20 points for processes
            
        except Exception as e:
            # Return 0 if calculation fails
            return 0.0

    def _calculate_financial_score(self) -> float:
        """
        Calculate financial performance score.
        """
        score = 0.0
        
        # 1. Revenue per active member scoring
        revenue_per_member_score = self._calculate_revenue_per_member_score()
        score += revenue_per_member_score
        
        # 2. Net profit margin scoring
        net_profit_margin_score = self._calculate_net_profit_margin_score()
        score += net_profit_margin_score
        
        # 3. Trend in profitability scoring
        profitability_trend_score = self._calculate_profitability_trend_score()
        score += profitability_trend_score
        
        # 4. Debt to net worth scoring
        debt_to_networth_score = self._calculate_debt_to_networth_score()
        score += debt_to_networth_score
        
        # 5. Current ratio scoring
        current_ratio_score = self._calculate_current_ratio_score()
        score += current_ratio_score
        
        # 6. Inventory period scoring
        inventory_period_score = self._calculate_inventory_period_score()
        score += inventory_period_score
        
        # 7. Accounts receivable scoring
        accounts_receivable_score = self._calculate_accounts_receivable_score()
        score += accounts_receivable_score
        
        # 8. Asset turnover scoring
        asset_turnover_score = self._calculate_asset_turnover_score()
        score += asset_turnover_score
        
        # 9. Cash dealings as percentage of gross revenue scoring
        cash_dealings_score = self._calculate_cash_dealings_score()
        score += cash_dealings_score
        
        # TODO: Implement other financial scoring components
        
        return min(score, 30.0)  # Cap at 30 points for financial

    def _calculate_net_profit_margin_score(self) -> float:
        """
        Calculate net profit margin score.
        Score: 3 if >= 10%, 2 if >= 5%, 1 if >= 0%, 0 if < 0%
        """
        financial_details = getattr(self.submission, 'financial_details_v2', None)
        
        if not financial_details:
            return 0.0
            
        net_profit = financial_details.current_year_net_profit or 0
        revenue = financial_details.current_year_revenue or 0
        
        if revenue > 0:
            profit_margin = (net_profit / revenue) * 100
            
            if profit_margin >= 10:
                return 3.0
            elif profit_margin >= 5:
                return 2.0
            elif profit_margin >= 0:
                return 1.0
        
        return 0.0

    def _calculate_profitability_trend_score(self) -> float:
        """
        Calculate trend in profitability score.
        Score: 3 if 3 profitable years, 2 if 2 years, 1 if 1 year, 0 if 0 years
        """
        financial_details = getattr(self.submission, 'financial_details_v2', None)
        
        if not financial_details:
            return 0.0
            
        profitable_years = 0
        
        # Check current year (2023-24)
        if (financial_details.current_year_net_profit or 0) > 0:
            profitable_years += 1
            
        # Check previous year (2022-23)
        if (financial_details.previous_year_net_profit or 0) > 0:
            profitable_years += 1
            
        # Check two years back (2021-22)
        if (financial_details.two_years_back_net_profit or 0) > 0:
            profitable_years += 1
        
        # Score based on number of profitable years
        if profitable_years >= 3:
            return 3.0
        elif profitable_years == 2:
            return 2.0
        elif profitable_years == 1:
            return 1.0
        else:
            return 0.0

    def _calculate_debt_to_networth_score(self) -> float:
        """
        Calculate debt to net worth score.
        Score: 3 if <= 3x, 2 if <= 6x, 1 if <= 10x, 0 if > 10x
        Lower debt-to-networth ratio is better
        """
        financial_details = getattr(self.submission, 'financial_details_v2', None)
        
        if not financial_details:
            return 0.0
            
        total_debt = financial_details.total_debt_today or 0
        current_net_worth = financial_details.current_year_net_worth
        
        # Handle edge cases: negative debt or zero/negative net worth
        if total_debt < 0 or current_net_worth <= 0:
            return 0.0
            
        # Calculate debt to net worth ratio
        debt_to_networth_ratio = (total_debt / current_net_worth) * 100
        
        # Range-based scoring as per new criteria
        if debt_to_networth_ratio <= 300:  # <= 3x (300%)
            return 3.0
        elif debt_to_networth_ratio <= 600:  # <= 6x (600%)
            return 2.0
        elif debt_to_networth_ratio <= 1000:  # <= 10x (1000%)
            return 1.0
        else:
            return 0.0  # > 10x

    def _calculate_current_ratio_score(self) -> float:
        """
        Calculate current ratio score.
        Score: 0 if 1, 1 if 1.5, 2 if 2, 3 if > 2
        Higher current ratio is better
        """
        financial_details = getattr(self.submission, 'financial_details_v2', None)
        
        if not financial_details:
            return 0.0
            
        current_assets = financial_details.current_year_current_assets or 0
        current_liabilities = financial_details.current_year_current_liabilities or 0
        
        # Handle edge cases: zero or negative liabilities
        if current_liabilities <= 0:
            return 0.0
            
        current_ratio = current_assets / current_liabilities
        
        # Scoring based on current ratio
        if current_ratio <= 1:
            return 0.0
        elif current_ratio <= 1.5:
            return 1.0
        elif current_ratio <= 2:
            return 2.0
        else:
            return 3.0  # Current ratio > 2

    def _calculate_inventory_period_score(self) -> float:
        """
        Calculate inventory period score.
        Score: 3 if < 30 days, 2 if >= 30 to < 60 days, 1 if >= 60 to < 90 days, 0 if >= 90 days
        Lower inventory period (faster turnover) is better
        """
        financial_details = getattr(self.submission, 'financial_details_v2', None)
        
        if not financial_details:
            return 3.0  # Return 3 points if no financial details (blank/inventory not tracked)
        
        opening_inventory = financial_details.current_year_opening_inventory or 0
        closing_inventory = financial_details.current_year_closing_inventory or 0
        cogs = financial_details.current_year_cogs or 0
        
        # Calculate average inventory
        average_inventory = (opening_inventory + closing_inventory) / 2
        
        # Handle edge cases where we can't calculate inventory period
        if average_inventory <= 0 or cogs <= 0:
            return 3.0  # Return 3 points (blank/not tracked)
        
        # Calculate inventory period (days inventory outstanding)
        inventory_turnover = cogs / average_inventory
        inventory_period = 365 / inventory_turnover
        
        # Score based on inventory period with tolerance for floating point precision
        # Use small tolerance (0.0001) to handle floating point precision issues
        if inventory_period < 30.0001:  # < 30 days = 3 points
            return 3.0
        elif inventory_period < 60.0001:  # >= 30 and < 60 days = 2 points
            return 2.0
        elif inventory_period < 90.0001:  # >= 60 and < 90 days = 1 point
            return 1.0
        else:  # >= 90 days = 0 points
            return 0.0

    def _calculate_accounts_receivable_score(self) -> float:
        """
        Calculate accounts receivable (days sales outstanding) score.
        Score: 0 if 90 days, 1 if 60 days, 2 if 30 days, 3 if blank/not provided
        Lower DSO (faster collection) is better
        """
        financial_details = getattr(self.submission, 'financial_details_v2', None)
        
        if not financial_details:
            return 3.0  # Return 3 points if no financial details (blank/not tracked)
        
        accounts_receivable = financial_details.current_year_accounts_receivable or 0
        revenue = financial_details.current_year_revenue or 0
        
        # Handle edge cases where we can't calculate DSO
        if accounts_receivable <= 0 or revenue <= 0:
            return 3.0  # Return 3 points (blank/not tracked)
        
        # Calculate Days Sales Outstanding (DSO)
        dso = (accounts_receivable / revenue) * 365
        
        # Score based on DSO with tolerance for floating point precision
        if dso <= 30.1:  # Allow small tolerance for floating point precision
            return 2.0
        elif dso <= 60.1:  # Allow small tolerance for floating point precision
            return 1.0
        elif dso <= 90.1:  # Allow small tolerance for floating point precision
            return 0.0
        else:
            # For DSO longer than 90 days, give 0 points
            return 0.0

    def _calculate_asset_turnover_score(self) -> float:
        """
        Calculate asset turnover ratio score.
        Score: 4 if 2.0, 3 if 1.5, 2 if 1.0, 1 if 0.5, 0 if blank/not provided
        Higher asset turnover is better
        """
        financial_details = getattr(self.submission, 'financial_details_v2', None)
        
        if not financial_details:
            return 0.0  # Return 0 points if no financial details (blank/not tracked)
        
        revenue = financial_details.current_year_revenue or 0
        assets = financial_details.current_year_assets or 0
        
        # Handle edge cases where we can't calculate asset turnover
        if revenue <= 0 or assets <= 0:
            return 0.0  # Return 0 points (blank/not tracked)
        
        # Calculate Asset Turnover Ratio
        asset_turnover = revenue / assets
        
        # Score based on asset turnover ratio with tolerance for floating point precision
        if asset_turnover >= 1.95:  # Allow small tolerance for floating point precision
            return 4.0
        elif asset_turnover >= 1.45:  # Allow small tolerance for floating point precision
            return 3.0
        elif asset_turnover >= 0.95:  # Allow small tolerance for floating point precision
            return 2.0
        elif asset_turnover >= 0.45:  # Allow small tolerance for floating point precision
            return 1.0
        else:
            # For asset turnover less than 0.5, give 0 points
            return 0.0
    
    def _calculate_cash_dealings_score(self) -> float:
        """
        Calculate cash dealings as percentage of gross revenue score.
        Score: 3 if < 20%, 2 if >= 20%, 1 if >= 50%, 0 if >= 70%
        Lower cash dealings percentage is better (indicates more digital transactions)
        """
        financial_details = getattr(self.submission, 'financial_details_v2', None)
        
        if not financial_details:
            return 0.0
            
        cash_dealings_percentage = financial_details.cash_cheque_percentage or 0
        
        # Score based on cash dealings percentage
        if cash_dealings_percentage >= 70:
            return 0.0
        elif cash_dealings_percentage >= 50:
            return 1.0
        elif cash_dealings_percentage >= 20:
            return 2.0
        else:
            return 3.0  # < 20%

    def _calculate_revenue_per_member_score(self) -> float:
        """
        Calculate revenue per active member score.
        Score: 3 if >= 100,000, 2 if >= 75,000, 1 if >= 50,000, 0 if < 50,000
        """
        fpo_details = getattr(self.submission, 'fpo_details', None)
        financial_details = getattr(self.submission, 'financial_details_v2', None)
        
        if not fpo_details or not financial_details:
            return 0.0
            
        revenue = financial_details.current_year_revenue or 0
        farmers_transacted = fpo_details.farmers_transacted or 0
        
        if farmers_transacted > 0:
            revenue_per_member = revenue / farmers_transacted
            
            if revenue_per_member >= 100000:
                return 3.0
            elif revenue_per_member >= 75000:
                return 2.0
            elif revenue_per_member >= 50000:
                return 1.0
        
        return 0.0