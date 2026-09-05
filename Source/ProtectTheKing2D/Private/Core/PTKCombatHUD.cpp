// Protect the King - 2D. Prototype combat HUD.

#include "Core/PTKCombatHUD.h"

#include "Characters/PTKEnemyCharacter.h"
#include "Characters/PTKKingCharacter.h"
#include "Characters/PTKTopDownCharacter.h"
#include "Components/PTKHealthComponent.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"
#include "ProtectTheKing2D.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKCombatHUD)

namespace PTKHUDColours
{
	static const FLinearColor Backdrop(0.02f, 0.02f, 0.03f, 0.78f);
	static const FLinearColor Border(0.55f, 0.58f, 0.66f, 0.95f);
	static const FLinearColor PlayerFill(0.16f, 0.72f, 0.30f, 1.0f);
	static const FLinearColor PlayerLow(0.85f, 0.28f, 0.16f, 1.0f);
	static const FLinearColor EnemyFill(0.86f, 0.16f, 0.16f, 1.0f);
	static const FLinearColor Text(0.92f, 0.94f, 0.98f, 1.0f);
	static const FLinearColor Dim(0.62f, 0.66f, 0.74f, 1.0f);
	/** Royal blue and gold, to read as the King rather than as another guard. */
	static const FLinearColor KingFill(0.30f, 0.46f, 0.92f, 1.0f);
	static const FLinearColor KingGold(0.94f, 0.78f, 0.32f, 1.0f);
}

APTKCombatHUD::APTKCombatHUD()
{
	PrimaryActorTick.bCanEverTick = false;
}

void APTKCombatHUD::DrawBar(float X, float Y, float Width, float Height,
	float Fraction, const FLinearColor& Fill)
{
	Fraction = FMath::Clamp(Fraction, 0.0f, 1.0f);

	// Border, then backdrop, then fill. Drawing the backdrop full width means
	// an empty bar still reads as a bar rather than vanishing.
	DrawRect(PTKHUDColours::Border, X - 1.0f, Y - 1.0f, Width + 2.0f, Height + 2.0f);
	DrawRect(PTKHUDColours::Backdrop, X, Y, Width, Height);
	if (Fraction > 0.0f)
	{
		DrawRect(Fill, X, Y, Width * Fraction, Height);
	}
}

void APTKCombatHUD::DrawPlayerPanel(APTKTopDownCharacter* Player)
{
	UPTKHealthComponent* const Health = Player->GetHealthComponent();
	if (!Health)
	{
		return;
	}

	const float X = 24.0f;
	const float Y = Canvas->SizeY - 64.0f;
	const float Fraction = Health->GetHealthFraction();

	// Turning the bar red under a quarter gives the state away at a glance,
	// without having to read the numbers.
	const FLinearColor Fill = (Fraction <= 0.25f)
		? PTKHUDColours::PlayerLow
		: PTKHUDColours::PlayerFill;

	DrawText(TEXT("RAVAGER"), PTKHUDColours::Text, X, Y - 20.0f, GEngine->GetMediumFont());
	DrawBar(X, Y, PlayerBarWidth, PlayerBarHeight, Fraction, Fill);

	const FString Numbers = FString::Printf(TEXT("%.0f / %.0f"),
		Health->GetCurrentHealth(), Health->GetMaxHealth());
	DrawText(Numbers, PTKHUDColours::Text,
		X + PlayerBarWidth + 12.0f, Y, GEngine->GetMediumFont());
}

void APTKCombatHUD::DrawEnemyBar(APTKEnemyCharacter* Enemy)
{
	UPTKHealthComponent* const Health = Enemy->GetHealthComponent();
	if (!Health || Health->IsDead())
	{
		return;
	}

	// Project from world space so the bar tracks the creature as it crawls.
	const FVector World = Enemy->GetActorLocation() + FVector(0.0f, 0.0f, EnemyBarWorldOffset);
	const FVector Screen = Project(World);

	// Behind the camera projects to a negative depth; drawing it would put a
	// mirrored bar on screen.
	if (Screen.Z <= 0.0f)
	{
		return;
	}

	const float X = Screen.X - EnemyBarWidth * 0.5f;
	const float Y = Canvas->SizeY - Screen.Y;

	DrawBar(X, Y, EnemyBarWidth, EnemyBarHeight,
		Health->GetHealthFraction(), PTKHUDColours::EnemyFill);

	const FString Label = FString::Printf(TEXT("%s  %.0f/%.0f"),
		*Enemy->GetEnemyDisplayName().ToString(),
		Health->GetCurrentHealth(), Health->GetMaxHealth());
	DrawText(Label, PTKHUDColours::Text, X, Y - 16.0f, GEngine->GetSmallFont());
}

void APTKCombatHUD::DrawDebugPanel(APTKTopDownCharacter* Player)
{
	float Y = 24.0f;
	const float X = 24.0f;
	UFont* const Font = GEngine->GetSmallFont();

	DrawText(TEXT("[F1] combat debug"), PTKHUDColours::Dim, X, Y, Font);
	Y += 18.0f;

	if (Player)
	{
		UPTKHealthComponent* const Health = Player->GetHealthComponent();
		DrawText(FString::Printf(TEXT("Ravager    HP %.0f/%.0f   %s   facing %s"),
			Health ? Health->GetCurrentHealth() : 0.0f,
			Health ? Health->GetMaxHealth() : 0.0f,
			*UPTKTypesLibrary::MovementStateToString(Player->GetMovementState()),
			*UPTKTypesLibrary::DirectionToString(Player->GetFacingDirection())),
			PTKHUDColours::Text, X, Y, Font);
		Y += 16.0f;
	}

	for (TActorIterator<APTKEnemyCharacter> It(GetWorld()); It; ++It)
	{
		APTKEnemyCharacter* const Enemy = *It;
		if (!IsValid(Enemy))
		{
			continue;
		}
		UPTKHealthComponent* const Health = Enemy->GetHealthComponent();
		const float Distance = Enemy->GetDistanceToTarget();

		DrawText(FString::Printf(
			TEXT("%-10s HP %.0f/%.0f   %s   facing %s   dist %s   cd %.2f"),
			*Enemy->GetEnemyId().ToString(),
			Health ? Health->GetCurrentHealth() : 0.0f,
			Health ? Health->GetMaxHealth() : 0.0f,
			*UPTKTypesLibrary::EnemyStateToString(Enemy->GetEnemyState()),
			*UPTKTypesLibrary::DirectionToString(Enemy->GetFacingDirection()),
			Distance < 0.0f ? TEXT("--") : *FString::Printf(TEXT("%.0f"), Distance),
			Enemy->GetAttackCooldownRemaining()),
			PTKHUDColours::Text, X, Y, Font);
		Y += 16.0f;
	}
}

void APTKCombatHUD::DrawDefeatBanner()
{
	const FString Message = TEXT("RAVAGER DEFEATED");
	float W = 0.0f;
	float H = 0.0f;
	GetTextSize(Message, W, H, GEngine->GetLargeFont());

	const float X = (Canvas->SizeX - W) * 0.5f;
	const float Y = Canvas->SizeY * 0.42f;

	DrawRect(PTKHUDColours::Backdrop, X - 24.0f, Y - 14.0f, W + 48.0f, H + 28.0f);
	DrawText(Message, PTKHUDColours::PlayerLow, X, Y, GEngine->GetLargeFont());
}

APTKKingCharacter* APTKCombatHUD::FindKing() const
{
	for (TActorIterator<APTKKingCharacter> It(GetWorld()); It; ++It)
	{
		if (IsValid(*It))
		{
			return *It;
		}
	}
	return nullptr;
}

void APTKCombatHUD::DrawKingPanel(APTKKingCharacter* King)
{
	UPTKHealthComponent* const Health = King->GetHealthComponent();
	if (!Health)
	{
		return;
	}

	// Top centre: the objective's health is the thing the whole mode is about,
	// so it does not compete with the player's bar in the corner.
	const float X = (Canvas->SizeX - KingBarWidth) * 0.5f;
	const float Y = 28.0f;

	DrawBar(X, Y, KingBarWidth, KingBarHeight, Health->GetHealthFraction(),
		King->IsDead() ? PTKHUDColours::PlayerLow : PTKHUDColours::KingFill);

	DrawText(TEXT("KING"), PTKHUDColours::KingGold, X, Y - 16.0f, GEngine->GetMediumFont());

	const FString Numbers = FString::Printf(TEXT("%.0f / %.0f   [%s]"),
		Health->GetCurrentHealth(), Health->GetMaxHealth(),
		*UPTKTypesLibrary::KingStateToString(King->GetKingState()));
	float W = 0.0f;
	float H = 0.0f;
	GetTextSize(Numbers, W, H, GEngine->GetMediumFont());
	DrawText(Numbers, PTKHUDColours::Text, X + KingBarWidth - W, Y - 16.0f,
		GEngine->GetMediumFont());
}

void APTKCombatHUD::DrawKingDefeatBanner()
{
	const FString Message = TEXT("KING DEFEATED");
	float W = 0.0f;
	float H = 0.0f;
	GetTextSize(Message, W, H, GEngine->GetLargeFont());

	const float X = (Canvas->SizeX - W) * 0.5f;
	const float Y = Canvas->SizeY * 0.30f;

	DrawRect(PTKHUDColours::Backdrop, X - 24.0f, Y - 14.0f, W + 48.0f, H + 28.0f);
	DrawText(Message, PTKHUDColours::KingGold, X, Y, GEngine->GetLargeFont());
}

void APTKCombatHUD::PTKKingAlertRadius(float Radius)
{
	if (APTKKingCharacter* const King = FindKing())
	{
		King->DebugSetAlertRadius(Radius);
	}
}

void APTKCombatHUD::LogKingInputIsolation()
{
	APTKKingCharacter* const King = FindKing();
	if (!King)
	{
		return;
	}

	APawn* const PlayerPawn = UGameplayStatics::GetPlayerPawn(this, 0);

	UE_LOG(LogPTK, Warning,
		TEXT("KINGTEST isolation  King IsA<APawn>=%d  IsPlayerPawn=%d  "
			 "Controller=%s  InputComponent=%s  PlayerPawn=%s"),
		King->IsA<APawn>() ? 1 : 0,
		(PlayerPawn == static_cast<AActor*>(King)) ? 1 : 0,
		King->GetInstigatorController() ? TEXT("PRESENT") : TEXT("none"),
		King->InputComponent ? TEXT("PRESENT") : TEXT("none"),
		PlayerPawn ? *PlayerPawn->GetClass()->GetName() : TEXT("none"));
}

void APTKCombatHUD::LogKingStatus(const FString& Stage)
{
	APTKKingCharacter* const King = FindKing();
	if (!King)
	{
		UE_LOG(LogPTK, Error, TEXT("KINGTEST %-22s no King in the level"), *Stage);
		return;
	}
	UPTKHealthComponent* const Health = King->GetHealthComponent();
	const FVector P = King->GetActorLocation();

	UE_LOG(LogPTK, Warning,
		TEXT("KINGTEST %-22s state=%-9s hp=%.0f/%.0f alerted=%d pos=(%.1f, %.1f, %.1f)"),
		*Stage,
		*UPTKTypesLibrary::KingStateToString(King->GetKingState()),
		Health ? Health->GetCurrentHealth() : -1.0f,
		Health ? Health->GetMaxHealth() : -1.0f,
		King->IsAlerted() ? 1 : 0,
		P.X, P.Y, P.Z);
}

void APTKCombatHUD::StartKingSelfTest()
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	UE_LOG(LogPTK, Warning, TEXT("KINGTEST sequence armed (-ptkkingtest)"));

	// One-shot, after everything has finished spawning and possessing.
	FTimerHandle IsolationHandle;
	World->GetTimerManager().SetTimer(IsolationHandle,
		FTimerDelegate::CreateWeakLambda(this, [this]() { LogKingInputIsolation(); }),
		1.5f, false);

	struct FStep
	{
		float Time;
		const TCHAR* Label;
		int32 Action;   // 0 log, 1 cast, 2 damage, 3 kill
		float Amount;
	};

	// Two damage steps land 0.15s apart on purpose: the second must be
	// SWALLOWED because a hit reaction is already playing. If it were not, the
	// flipbook would restart and the King would twitch on frame 1 forever.
	static const FStep Steps[] = {
		{ 2.0f,  TEXT("baseline"),           0, 0.0f },
		// Shrink the radius so no enemy qualifies: he must fall back to Idle.
		{ 3.0f,  TEXT("radius-1"),           4, 1.0f },
		{ 3.4f,  TEXT("expect-idle"),        0, 0.0f },
		{ 4.0f,  TEXT("idle"),               5, 0.0f },
		// Restore it: the same enemies now qualify again and he must re-alert.
		{ 5.0f,  TEXT("radius-600"),         4, 600.0f },
		{ 5.4f,  TEXT("expect-alert"),       0, 0.0f },
		{ 6.0f,  TEXT("alert"),              5, 0.0f },
		{ 7.0f,  TEXT("cast-fired"),         1, 0.0f },
		{ 7.3f,  TEXT("during-cast"),        0, 0.0f },
		{ 7.35f, TEXT("powercast"),          5, 0.0f },
		{ 7.5f,  TEXT("cast-during-cast"),   1, 0.0f },
		{ 9.0f,  TEXT("after-cast"),         0, 0.0f },
		{ 11.0f, TEXT("damage-1"),           2, 500.0f },
		{ 11.15f,TEXT("damage-2-rapid"),     2, 500.0f },
		{ 11.4f, TEXT("during-hit"),         0, 0.0f },
		{ 13.0f, TEXT("after-hit"),          0, 0.0f },
		{ 15.0f, TEXT("kill"),               3, 0.0f },
		{ 15.4f, TEXT("just-died"),          0, 0.0f },
		{ 16.5f, TEXT("dead"),               5, 0.0f },
		{ 18.0f, TEXT("damage-after-death"), 2, 500.0f },
		{ 18.5f, TEXT("cast-after-death"),   1, 0.0f },
		{ 19.0f, TEXT("final"),              0, 0.0f },
	};

	for (const FStep& Step : Steps)
	{
		const FString Label(Step.Label);
		const int32 Action = Step.Action;
		const float Amount = Step.Amount;

		FTimerHandle Handle;
		World->GetTimerManager().SetTimer(Handle,
			FTimerDelegate::CreateWeakLambda(this, [this, Label, Action, Amount]()
			{
				switch (Action)
				{
				case 1:
					UE_LOG(LogPTK, Warning, TEXT("KINGTEST -> TriggerPowerCast()"));
					PTKKingCast();
					break;
				case 2:
					UE_LOG(LogPTK, Warning, TEXT("KINGTEST -> damage %.0f"), Amount);
					PTKKingDamage(Amount);
					break;
				case 3:
					UE_LOG(LogPTK, Warning, TEXT("KINGTEST -> kill"));
					PTKKingKill();
					break;
				case 4:
					UE_LOG(LogPTK, Warning, TEXT("KINGTEST -> AlertRadius = %.0f"), Amount);
					PTKKingAlertRadius(Amount);
					break;
				case 5:
					// Captured so the sprite can be eyeballed for the two things
					// a log cannot show: a frame going missing, and the pivot or
					// scale jumping between states.
					UE_LOG(LogPTK, Warning, TEXT("KINGTEST -> screenshot %s"), *Label);
					if (APlayerController* const PC = GetOwningPlayerController())
					{
						PC->ConsoleCommand(FString::Printf(
							TEXT("HighResShot 1280x720 filename=king_%s"), *Label), true);
					}
					break;
				default:
					break;
				}
				LogKingStatus(Label);
			}), Step.Time, false);
	}
}

void APTKCombatHUD::BeginPlay()
{
	Super::BeginPlay();

	if (FParse::Param(FCommandLine::Get(), TEXT("ptkkingtest")))
	{
		StartKingSelfTest();
	}
}

void APTKCombatHUD::PTKKingCast()
{
	if (APTKKingCharacter* const King = FindKing())
	{
		const bool bStarted = King->TriggerPowerCast();
		UE_LOG(LogTemp, Log, TEXT("PTKKingCast: %s"),
			bStarted ? TEXT("started") : TEXT("refused (dead, or already casting)"));
	}
}

void APTKCombatHUD::PTKKingDamage(float Amount)
{
	if (APTKKingCharacter* const King = FindKing())
	{
		King->DebugApplyDamage(Amount);
	}
}

void APTKCombatHUD::PTKKingKill()
{
	if (APTKKingCharacter* const King = FindKing())
	{
		if (UPTKHealthComponent* const Health = King->GetHealthComponent())
		{
			King->DebugApplyDamage(Health->GetCurrentHealth());
		}
	}
}

void APTKCombatHUD::DrawHUD()
{
	Super::DrawHUD();

	if (!Canvas)
	{
		return;
	}

	APTKTopDownCharacter* const Player =
		Cast<APTKTopDownCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));

	if (Player)
	{
		DrawPlayerPanel(Player);
	}

	for (TActorIterator<APTKEnemyCharacter> It(GetWorld()); It; ++It)
	{
		if (IsValid(*It))
		{
			DrawEnemyBar(*It);
		}
	}

	if (bShowDebugPanel)
	{
		DrawDebugPanel(Player);
	}

	APTKKingCharacter* const King = FindKing();
	if (King)
	{
		DrawKingPanel(King);
	}

	if (Player && Player->IsDead())
	{
		DrawDefeatBanner();
	}

	if (King && King->IsDead())
	{
		DrawKingDefeatBanner();
	}
}
