"""
Deep Derivatives Analysis - Accel-Jerk Divergence Study
"""
import polars as pl

def main():
    print("="*60)
    print("DEEP DERIVATIVES ANALYSIS")
    print("="*60)
    
    # Load all data - allow extra columns
    print("\n[1] Loading derivatives data...")
    df = pl.scan_parquet('C:/fast_swarm/data/derivatives/**/*.parquet', allow_missing_columns=True)
    
    # Get schema and row count
    schema = df.collect_schema()
    row_count = df.select(pl.len()).collect().item()
    print(f"    Total rows: {row_count:,}")
    print(f"    Total columns: {len(schema)}")
    
    # Get symbol/timeframe breakdown
    breakdown = df.group_by(['symbol', 'timeframe']).agg(pl.len().alias('rows')).collect()
    print("\n[2] Data breakdown:")
    for row in breakdown.sort(['symbol', 'timeframe']).iter_rows(named=True):
        print(f"    {row['symbol']:8} {row['timeframe']:4} -> {row['rows']:>10,} rows")
    
    # Focus on close price derivatives for the core analysis
    print("\n[3] Analyzing close price derivatives (accel-jerk divergence)...")
    
    # Check which columns exist
    cols_needed = ['symbol', 'timeframe', 'close', 'close_velocity', 'close_acceleration', 'close_jerk']
    available = [c for c in cols_needed if c in schema.names()]
    print(f"    Available columns: {available}")
    
    # Load just what we need, filtering nulls
    analysis_df = df.select(available).filter(
        pl.col('close_acceleration').is_not_null() & 
        pl.col('close_jerk').is_not_null()
    ).collect()
    
    print(f"    Rows with valid accel/jerk: {len(analysis_df):,}")
    
    # Add future returns (1, 5, 10, 20 periods ahead)
    for periods in [1, 5, 10, 20]:
        analysis_df = analysis_df.with_columns([
            ((pl.col('close').shift(-periods) - pl.col('close')) / pl.col('close') * 100)
            .alias(f'return_{periods}')
        ])
    
    # Add divergence flags
    analysis_df = analysis_df.with_columns([
        # Accel-Jerk divergence
        ((pl.col('close_jerk') > 0) != (pl.col('close_acceleration') > 0)).alias('accel_jerk_divergent'),
        # Specific states
        ((pl.col('close_jerk') > 0) & (pl.col('close_acceleration') < 0)).alias('jerk_pos_accel_neg'),
        ((pl.col('close_jerk') < 0) & (pl.col('close_acceleration') > 0)).alias('jerk_neg_accel_pos'),
        # Velocity direction
        (pl.col('close_velocity') > 0).alias('vel_positive'),
        # Triple divergence (vel vs accel vs jerk)
        ((pl.col('close_velocity') > 0) != (pl.col('close_acceleration') > 0)).alias('vel_accel_divergent'),
    ])
    
    # Remove rows where future returns are null
    analysis_df = analysis_df.filter(pl.col('return_1').is_not_null())
    print(f"    Rows with valid future returns: {len(analysis_df):,}")
    
    print("\n[4] Accel-Jerk Divergence Analysis:")
    print("-"*60)
    
    # Core divergence analysis
    for condition_name, condition_col in [
        ("Divergent (jerk & accel opposite)", 'accel_jerk_divergent'),
        ("Jerk+ Accel- (momentum building)", 'jerk_pos_accel_neg'),
        ("Jerk- Accel+ (momentum fading)", 'jerk_neg_accel_pos'),
    ]:
        subset = analysis_df.filter(pl.col(condition_col))
        not_subset = analysis_df.filter(~pl.col(condition_col))
        
        print(f"\n    {condition_name}:")
        print(f"    Count: {len(subset):,} ({len(subset)/len(analysis_df)*100:.1f}%)")
        
        for periods in [1, 5, 10, 20]:
            col = f'return_{periods}'
            cond_mean = subset[col].mean()
            base_mean = not_subset[col].mean()
            cond_pos = (subset[col] > 0).sum() / len(subset) * 100
            base_pos = (not_subset[col] > 0).sum() / len(not_subset) * 100
            
            edge = cond_pos - base_pos
            print(f"      {periods:2}p: P(up)={cond_pos:5.1f}% vs {base_pos:5.1f}% baseline | Edge: {edge:+5.2f}% | Mean ret: {cond_mean:+.4f}% vs {base_mean:+.4f}%")
    
    print("\n[5] By Symbol Analysis (1-period return):")
    print("-"*60)
    
    for symbol in analysis_df['symbol'].unique().sort().to_list():
        sym_df = analysis_df.filter(pl.col('symbol') == symbol)
        
        div_df = sym_df.filter(pl.col('accel_jerk_divergent'))
        align_df = sym_df.filter(~pl.col('accel_jerk_divergent'))
        
        if len(div_df) > 100 and len(align_df) > 100:
            div_pup = (div_df['return_1'] > 0).sum() / len(div_df) * 100
            align_pup = (align_df['return_1'] > 0).sum() / len(align_df) * 100
            edge = div_pup - align_pup
            
            print(f"    {symbol:8} | Divergent P(up): {div_pup:5.1f}% | Aligned P(up): {align_pup:5.1f}% | Edge: {edge:+5.2f}%")
    
    print("\n[6] By Timeframe Analysis:")
    print("-"*60)
    
    for tf in analysis_df['timeframe'].unique().sort().to_list():
        tf_df = analysis_df.filter(pl.col('timeframe') == tf)
        
        div_df = tf_df.filter(pl.col('accel_jerk_divergent'))
        align_df = tf_df.filter(~pl.col('accel_jerk_divergent'))
        
        if len(div_df) > 100 and len(align_df) > 100:
            div_pup = (div_df['return_1'] > 0).sum() / len(div_df) * 100
            align_pup = (align_df['return_1'] > 0).sum() / len(align_df) * 100
            edge = div_pup - align_pup
            
            print(f"    {tf:8} | Divergent P(up): {div_pup:5.1f}% | Aligned P(up): {align_pup:5.1f}% | Edge: {edge:+5.2f}% | n={len(div_df):,}")

    print("\n[7] Combined Signal Analysis:")
    print("-"*60)
    
    # Triple condition: vel vs accel divergent AND accel vs jerk divergent
    triple_div = analysis_df.filter(
        pl.col('vel_accel_divergent') & pl.col('accel_jerk_divergent')
    )
    
    if len(triple_div) > 100:
        baseline_pup = (analysis_df['return_1'] > 0).sum() / len(analysis_df) * 100
        triple_pup = (triple_div['return_1'] > 0).sum() / len(triple_div) * 100
        edge = triple_pup - baseline_pup
        
        print(f"    Triple divergence (vel-accel AND accel-jerk both divergent):")
        print(f"    Count: {len(triple_div):,} ({len(triple_div)/len(analysis_df)*100:.1f}%)")
        print(f"    P(up): {triple_pup:.1f}% vs {baseline_pup:.1f}% baseline | Edge: {edge:+.2f}%")
        
        # By specific state
        for state_name, vel_cond, accel_cond, jerk_cond in [
            ("Rising but decelerating, decel easing", True, False, True),
            ("Falling but accel positive, accel fading", False, True, False),
        ]:
            state_df = analysis_df.filter(
                (pl.col('vel_positive') == vel_cond) &
                ((pl.col('close_acceleration') > 0) == accel_cond) &
                ((pl.col('close_jerk') > 0) == jerk_cond)
            )
            if len(state_df) > 100:
                state_pup = (state_df['return_1'] > 0).sum() / len(state_df) * 100
                state_edge = state_pup - baseline_pup
                print(f"\n    {state_name}:")
                print(f"    Count: {len(state_df):,} | P(up): {state_pup:.1f}% | Edge: {state_edge:+.2f}%")
    
    print("\n" + "="*60)
    print("ANALYSIS COMPLETE")
    print("="*60)

if __name__ == "__main__":
    main()
