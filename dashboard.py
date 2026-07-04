import pandas as pd


def analyze_data():
    df_metadata_2 = pd.read_csv("metadata_new.csv")
    df_friend_no_hover_2 = pd.read_csv("friend_no_hover_new.csv")
    df_user_reaction_2 = pd.read_csv("user_reaction_new.csv")

    # thoi gian chay luong user_reaction->about->photo
    time_execute_tb_user_reaction = df_user_reaction_2["time_execute"].mean() + 20
    so_luong_user_reaction = df_user_reaction_2["count_entity"].sum()
    tb_user_reaction = so_luong_user_reaction / len(df_user_reaction_2)

    # thoi gian chay luong hybird user_reaction -> friends(no_hover) -> about -> photo
    time_execute_tb_friend_no_hover = (
        df_friend_no_hover_2["time_execute"].mean()
        + df_user_reaction_2["time_execute"].mean()
        + 13
    )
    so_luong_friend = (
        df_friend_no_hover_2["total_user_extract"].sum() + so_luong_user_reaction
    )
    tb_extract_user_hybird = so_luong_friend / len(df_friend_no_hover_2)

    # thoi gian chay luong home->friend_no_ hover)->about->photo
    time_execute_tb_home_friend_no_hover = (
        df_friend_no_hover_2["time_execute"].mean() + 20 + 13
    )
    so_luong_friend_no_hover = df_friend_no_hover_2["total_user_extract"].sum()
    tb_extraac_user_no_hover = so_luong_friend_no_hover / len(df_friend_no_hover_2)

    print("=" * 70)
    print("1. LUỒNG: USER_REACTION -> ABOUT -> PHOTO")
    print("=" * 70)
    print(
        f"Thời gian thực thi trung bình : {time_execute_tb_user_reaction/60 :.2f} phút"
    )
    print(f"Tổng số bạn bè thu thập         : {so_luong_user_reaction}")
    print(f"Số bạn bè thu thập trung bình mỗi lần    : {tb_user_reaction:.2f}")

    print("\n" + "=" * 70)
    print("2. LUỒNG: USER_REACTION -> FRIEND(NO_HOVER) -> ABOUT -> PHOTO")
    print("=" * 70)
    print(
        f"Thời gian thực thi trung bình : {time_execute_tb_friend_no_hover /60 :.2f} phút"
    )
    print(f"Tổng số bạn bè thu thập         : {so_luong_friend}")
    print(f"Số bạn bè thu thập trung bình mỗi lần    : {tb_extract_user_hybird:.2f}")

    print("\n" + "=" * 70)
    print("3. LUỒNG: HOME -> FRIEND(NO_HOVER) -> ABOUT -> PHOTO")
    print("=" * 70)
    print(
        f"Thời gian thực thi trung bình : {time_execute_tb_home_friend_no_hover/60:.2f} phút"
    )
    print(f"Tổng số bạn bè thu thập         : {so_luong_friend_no_hover}")
    print(f"Số bạn bè thu thập trung bình mỗi lần    : {tb_extraac_user_no_hover:.2f}")


def phantich_result_2():
    pass


if __name__ == "__main__":
    analyze_data()
