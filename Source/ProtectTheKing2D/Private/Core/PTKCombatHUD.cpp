// Protect the King - 2D. Prototype combat HUD.

#include "Core/PTKCombatHUD.h"

#include "Characters/PTKEnemyCharacter.h"
#include "Characters/PTKGuardCharacter.h"
#include "Characters/PTKKingCharacter.h"
#include "Characters/PTKTopDownCharacter.h"
#include "Components/PTKHealthComponent.h"
#include "AI/PTKGuardAIController.h"
#include "Core/PTKBattlefield.h"
#include "Core/PTKGameModeBase.h"
#include "Core/PTKGuardBase.h"
#include "Core/PTKPlayerController.h"
#include "Core/PTKSpawnPortal.h"
#include "Core/PTKWaveManager.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/OverlapResult.h"
#include "Engine/Texture2D.h"
#include "EngineUtils.h"
#include "InputCoreTypes.h"
#include "InputKeyEventArgs.h"
#include "Kismet/GameplayStatics.h"
#include "ProtectTheKing2D.h"
#include "UObject/ConstructorHelpers.h"

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

	static const FLinearColor Selected(1.0f, 0.84f, 0.28f, 1.0f);
	static const FLinearColor Dead(0.42f, 0.20f, 0.20f, 1.0f);
	static const FLinearColor DeadText(0.60f, 0.42f, 0.42f, 1.0f);
	static const FLinearColor BaseFill(0.32f, 0.68f, 0.90f, 1.0f);
	static const FLinearColor Warning(1.0f, 0.36f, 0.22f, 1.0f);
	static const FLinearColor Boosted(1.0f, 0.55f, 0.95f, 1.0f);
	static const FLinearColor Victory(0.42f, 0.94f, 0.52f, 1.0f);
}

APTKCombatHUD::APTKCombatHUD()
{
	PrimaryActorTick.bCanEverTick = false;

	// The minimap art is resolved lazily in DrawMinimap rather than by a
	// ConstructorHelpers finder. A finder runs while the CDO is being built,
	// which on a fresh clone - before the map has been imported - logs a hard
	// "Failed to find" error for an asset that is legitimately not there yet.
	// A soft path fails quietly and simply draws the flat panel instead.
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

	DrawText(PlayerLabel(Player), PTKHUDColours::Text, X, Y - 20.0f, GEngine->GetMediumFont());
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
		// Named from the pawn, not hard-coded: with more than one guard in the
		// project a fixed label would quietly lie about who is being played.
		DrawText(FString::Printf(TEXT("%-10s HP %.0f/%.0f   %s   facing %s"),
			*Player->GetClass()->GetName().Replace(TEXT("BP_"), TEXT("")).Replace(TEXT("_C"), TEXT("")),
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

		// Target is printed by name and first, because the question this panel
		// exists to answer is "what is it actually going for" - which is how a
		// failed hand-off from a dead guard to the King is spotted at a glance.
		DrawText(FString::Printf(
			TEXT("%-10s HP %.0f/%.0f  Target: %-16s  AI: %-6s  Dist: %-5s  Range: %.0f  cd %.2f"),
			*Enemy->GetEnemyId().ToString(),
			Health ? Health->GetCurrentHealth() : 0.0f,
			Health ? Health->GetMaxHealth() : 0.0f,
			Enemy->GetTarget() ? *Enemy->GetTarget()->GetName() : TEXT("none"),
			*UPTKTypesLibrary::EnemyStateToString(Enemy->GetEnemyState()),
			Distance < 0.0f ? TEXT("--") : *FString::Printf(TEXT("%.0f"), Distance),
			Enemy->GetAttackReach(),
			Enemy->GetAttackCooldownRemaining()),
			PTKHUDColours::Text, X, Y, Font);
		Y += 16.0f;
	}
}

FString APTKCombatHUD::PlayerLabel(APTKTopDownCharacter* Player) const
{
	// Whoever is actually being played, not whoever was being played when this
	// HUD was written. PTKPlayGuard can put Aegis or Wraith behind the same
	// bar, and a panel that still said RAVAGER would be reporting the wrong
	// character's health to the player.
	if (const APTKGuardCharacter* const Guard = Cast<APTKGuardCharacter>(Player))
	{
		if (!Guard->GetGuardDisplayName().IsEmpty())
		{
			return Guard->GetGuardDisplayName().ToString().ToUpper();
		}
		if (!Guard->GetGuardId().IsNone())
		{
			return Guard->GetGuardId().ToString().ToUpper();
		}
	}
	return TEXT("GUARD");
}

void APTKCombatHUD::DrawDefeatBanner()
{
	const FString Message = PlayerLabel(
		Cast<APTKTopDownCharacter>(UGameplayStatics::GetPlayerPawn(this, 0))) + TEXT(" DEFEATED");
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

void APTKCombatHUD::PTKGuardMove(float X, float Y, float Duration, float StartDelay)
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	const FVector2D Input(X, Y);
	const float End = FMath::Max(Duration, 0.05f);

	// Movement input is consumed every frame, so it has to be re-applied every
	// frame for the whole window - a single call would move him for one tick.
	TSharedPtr<float> Elapsed = MakeShared<float>(0.0f);
	TSharedPtr<FTimerHandle> Repeat = MakeShared<FTimerHandle>();

	FTimerHandle Start;
	World->GetTimerManager().SetTimer(Start,
		FTimerDelegate::CreateWeakLambda(this, [this, Input, End, Elapsed, Repeat]()
		{
			UWorld* const W = GetWorld();
			if (!W) { return; }
			UE_LOG(LogPTK, Warning, TEXT("PTKGuardMove: input (%.0f, %.0f) for %.1fs"),
				Input.X, Input.Y, End);
			W->GetTimerManager().SetTimer(*Repeat,
				FTimerDelegate::CreateWeakLambda(this, [this, Input, End, Elapsed, Repeat]()
				{
					UWorld* const W2 = GetWorld();
					if (!W2) { return; }
					*Elapsed += 0.016f;
					APTKTopDownCharacter* const Guard =
						Cast<APTKTopDownCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
					if (Guard && *Elapsed < End)
					{
						Guard->SetMoveInput(Input);
					}
					else
					{
						if (Guard) { Guard->SetMoveInput(FVector2D::ZeroVector); }
						W2->GetTimerManager().ClearTimer(*Repeat);
					}
				}), 0.016f, true);
		}), FMath::Max(StartDelay, 0.01f), false);
}

void APTKCombatHUD::PTKPlayGuard(const FString& GuardName)
{
	UWorld* const World = GetWorld();
	APlayerController* const PC = GetOwningPlayerController();
	if (!World || !PC)
	{
		return;
	}

	const FString Path = FString::Printf(
		TEXT("/Game/PTK/Characters/Guards/%s/Blueprints/BP_%s.BP_%s_C"),
		*GuardName, *GuardName, *GuardName);
	UClass* const GuardClass = LoadClass<APTKTopDownCharacter>(nullptr, *Path);
	if (!GuardClass)
	{
		UE_LOG(LogPTK, Error, TEXT("PTKPlayGuard: no guard Blueprint at %s"), *Path);
		return;
	}

	APawn* const Old = PC->GetPawn();
	const FTransform Where = Old ? Old->GetActorTransform() : FTransform::Identity;

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride =
		ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
	APTKTopDownCharacter* const Guard =
		World->SpawnActor<APTKTopDownCharacter>(GuardClass, Where, Params);
	if (!Guard)
	{
		UE_LOG(LogPTK, Error, TEXT("PTKPlayGuard: could not spawn %s"), *GuardName);
		return;
	}

	PC->UnPossess();
	PC->Possess(Guard);

	// The previous guard must go, not merely be un-possessed: enemies pick the
	// nearest LIVING guard, so leaving Ravager standing there would quietly
	// make this a two-guard test.
	if (Old)
	{
		Old->Destroy();
	}

	UE_LOG(LogPTK, Warning, TEXT("PTKPlayGuard: now playing %s"), *Guard->GetName());
}

void APTKCombatHUD::PTKKillGuards(float Delay)
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	FTimerHandle Handle;
	World->GetTimerManager().SetTimer(Handle,
		FTimerDelegate::CreateWeakLambda(this, [this]()
		{
			UWorld* const W = GetWorld();
			if (!W)
			{
				return;
			}
			int32 Felled = 0;
			for (TActorIterator<APTKGuardCharacter> It(W); It; ++It)
			{
				APTKGuardCharacter* const Guard = *It;
				if (!Guard || Guard->IsDead())
				{
					continue;
				}
				if (UPTKHealthComponent* const Health = Guard->GetHealthComponent())
				{
					UE_LOG(LogPTK, Warning,
						TEXT("*** DEBUG KILL (console command, NOT gameplay) *** ")
						TEXT("felling %s from %.0f HP"), *Guard->GetName(),
						Health->GetCurrentHealth());
					Health->ApplyDamage(Health->GetCurrentHealth(), Guard);
					++Felled;
				}
			}
			UE_LOG(LogPTK, Warning, TEXT("PTKKillGuards: felled %d guard(s)"), Felled);
		}), FMath::Max(Delay, 0.01f), false);

	UE_LOG(LogPTK, Warning, TEXT("PTKKillGuards: scheduled at +%.1fs"), Delay);
}

void APTKCombatHUD::PTKGuardDefend(int32 Count, float Interval, float StartDelay)
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	Count = FMath::Clamp(Count, 1, 60);
	Interval = FMath::Max(Interval, 0.1f);

	for (int32 i = 0; i < Count; ++i)
	{
		FTimerHandle Handle;
		World->GetTimerManager().SetTimer(Handle,
			FTimerDelegate::CreateWeakLambda(this, [this]()
			{
				APTKTopDownCharacter* const Player =
					Cast<APTKTopDownCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
				if (Player)
				{
					Player->StartDefend();
				}
			}), FMath::Max(StartDelay + i * Interval, 0.01f), false);
	}

	UE_LOG(LogPTK, Warning, TEXT("PTKGuardDefend: %d block(s), every %.1fs, starting at +%.1fs"),
		Count, Interval, StartDelay);
}

void APTKCombatHUD::PTKGuardKill(float Delay)
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	FTimerHandle Handle;
	World->GetTimerManager().SetTimer(Handle,
		FTimerDelegate::CreateWeakLambda(this, [this]()
		{
			APTKTopDownCharacter* const Player =
				Cast<APTKTopDownCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
			if (!Player)
			{
				return;
			}
			if (UPTKHealthComponent* const Health = Player->GetHealthComponent())
			{
				// Shouted, not whispered. This applies the guard's ENTIRE
				// remaining health as a single blow, so in a log it looks
				// identical to "he suddenly died for no reason" - the one thing
				// that must never be mistaken for gameplay. If this line is
				// absent, the death was not caused by a debug command.
				UE_LOG(LogPTK, Warning,
					TEXT("*** DEBUG KILL (console command, NOT gameplay) *** ")
					TEXT("felling %s from %.0f HP in one blow"),
					*Player->GetName(), Health->GetCurrentHealth());
				Health->ApplyDamage(Health->GetCurrentHealth(), Player);
			}
		}), FMath::Max(Delay, 0.01f), false);
}

void APTKCombatHUD::PTKShot(float Delay, const FString& Name)
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	const FString Safe = Name;
	FTimerHandle Handle;
	World->GetTimerManager().SetTimer(Handle,
		FTimerDelegate::CreateWeakLambda(this, [this, Safe]()
		{
			if (APlayerController* const PC = GetOwningPlayerController())
			{
				UE_LOG(LogPTK, Warning, TEXT("PTKShot: capturing king_%s"), *Safe);
				PC->ConsoleCommand(FString::Printf(
					TEXT("HighResShot 1280x720 filename=king_%s"), *Safe), true);
			}
		}), FMath::Max(Delay, 0.01f), false);
}

void APTKCombatHUD::PTKKingHeartbeat(int32 bEnabled)
{
	if (APTKKingCharacter* const King = FindKing())
	{
		King->DebugSetHealthHeartbeat(bEnabled != 0);
		UE_LOG(LogPTK, Warning, TEXT("King health heartbeat %s"),
			bEnabled ? TEXT("ON") : TEXT("OFF"));
	}
}

void APTKCombatHUD::PTKGuardAttack(int32 Count, float Interval, float StartDelay)
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	Count = FMath::Clamp(Count, 1, 60);
	Interval = FMath::Max(Interval, 0.1f);

	for (int32 i = 0; i < Count; ++i)
	{
		FTimerHandle Handle;
		World->GetTimerManager().SetTimer(Handle,
			FTimerDelegate::CreateWeakLambda(this, [this]()
			{
				APTKTopDownCharacter* const Player =
					Cast<APTKTopDownCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
				if (Player)
				{
					Player->StartAttack();
				}
			}), FMath::Max(StartDelay + i * Interval, 0.01f), false);
	}

	UE_LOG(LogPTK, Warning, TEXT("PTKGuardAttack: %d swing(s), every %.1fs, starting at +%.1fs"),
		Count, Interval, StartDelay);
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

void APTKCombatHUD::PTKKingTest()
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	UE_LOG(LogPTK, Warning,
		TEXT("KINGTEST sequence started BY HAND - this damages and kills the King"));

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

	// Enemy bars are still drawn per enemy, but only for the ones actually on
	// screen - DrawEnemyBar rejects anything the projection puts outside the
	// viewport, which at a 30-strong horde spread over a 5000-unit map is most
	// of them.
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

	DrawGuardRoster();
	DrawWavePanel();
	DrawMinimap();
	DrawWorldLabels();
	DrawWarnings();
	DrawResultBanner();

	// The old banners only fire while the run is still notionally live; once a
	// result exists DrawResultBanner owns the centre of the screen.
	const APTKGameModeBase* Mode = GetWorld() ? GetWorld()->GetAuthGameMode<APTKGameModeBase>() : nullptr;
	const bool bMatchOver = Mode && Mode->IsMatchOver();

	if (!bMatchOver && Player && Player->IsDead())
	{
		DrawDefeatBanner();
	}
}

// ===========================================================================
// The real game HUD
// ===========================================================================

const APTKBattlefield* APTKCombatHUD::GetBattlefield() const
{
	return APTKBattlefield::Get(GetWorld());
}

APTKWaveManager* APTKCombatHUD::GetWaveManager() const
{
	return APTKWaveManager::Get(GetWorld());
}

void APTKCombatHUD::DrawPanel(float X, float Y, float W, float H, float Alpha)
{
	DrawRect(FLinearColor(0.02f, 0.02f, 0.03f, Alpha), X, Y, W, H);
	DrawRect(PTKHUDColours::Border, X, Y, W, 1.0f);
	DrawRect(PTKHUDColours::Border, X, Y + H - 1.0f, W, 1.0f);
	DrawRect(PTKHUDColours::Border, X, Y, 1.0f, H);
	DrawRect(PTKHUDColours::Border, X + W - 1.0f, Y, 1.0f, H);
}

float APTKCombatHUD::DrawCentredText(const FString& Text, float CentreX, float Y,
	const FLinearColor& Colour, float Scale)
{
	float W = 0.0f;
	float H = 0.0f;
	GetTextSize(Text, W, H, GEngine->GetMediumFont(), Scale);
	DrawText(Text, Colour, CentreX - W * 0.5f, Y, GEngine->GetMediumFont(), Scale);
	return W;
}

// ---------------------------------------------------------------------------
// Guard roster: all five, always, plus the King.
//
// The point of this panel is the switching decision - the player has to be able
// to see a guard dying somewhere off screen and press its number. So every
// guard is listed whether or not it is visible, and a dead one keeps its ROW
// (greyed, marked DEAD) rather than disappearing: a vanishing row would
// renumber the ones below it and make the number keys lie.
// ---------------------------------------------------------------------------

void APTKCombatHUD::DrawGuardRoster()
{
	const APTKBattlefield* Field = GetBattlefield();
	APTKPlayerController* const PC = Cast<APTKPlayerController>(GetOwningPlayerController());
	if (!Field || !PC)
	{
		return;
	}

	const TArray<FName>& Order = PC->GetGuardOrder();
	if (Order.Num() == 0)
	{
		return;
	}

	const float X = 18.0f;
	const float RowH = RosterRowHeight;
	const float PanelH = RowH * (Order.Num() + 1) + 14.0f;
	const float Y = Canvas->SizeY * 0.5f - PanelH * 0.5f;

	DrawPanel(X - 8.0f, Y - 8.0f, RosterWidth + 16.0f, PanelH + 12.0f);

	const APTKGuardCharacter* Played = PC->GetPlayerGuard();

	for (int32 Slot = 1; Slot <= Order.Num(); ++Slot)
	{
		APTKGuardCharacter* const Guard = PC->GetGuardInSlot(Slot);
		const float RowY = Y + (Slot - 1) * RowH;

		const bool bSelected = Guard && Guard == Played;
		const bool bDead = !Guard || Guard->IsDead();

		if (bSelected)
		{
			// A filled highlight rather than a coloured name: the selected guard
			// has to be findable in peripheral vision during a fight.
			DrawRect(FLinearColor(PTKHUDColours::Selected.R, PTKHUDColours::Selected.G,
				PTKHUDColours::Selected.B, 0.18f), X - 4.0f, RowY - 2.0f, RosterWidth + 8.0f, RowH);
		}

		const FLinearColor NameColour = bDead ? PTKHUDColours::DeadText
			: (bSelected ? PTKHUDColours::Selected : PTKHUDColours::Text);

		const FString Label = FString::Printf(TEXT("%d %s"), Slot,
			*Order[Slot - 1].ToString().ToUpper());
		DrawText(Label, NameColour, X, RowY, GEngine->GetSmallFont());

		const float BarX = X + 92.0f;
		const float BarW = RosterWidth - 96.0f;

		if (bDead)
		{
			DrawBar(BarX, RowY + 3.0f, BarW, 9.0f, 0.0f, PTKHUDColours::Dead);
			DrawText(TEXT("DEAD"), PTKHUDColours::DeadText, BarX + 2.0f, RowY + 1.0f,
				GEngine->GetSmallFont());
			continue;
		}

		UPTKHealthComponent* const Health = Guard->GetHealthComponent();
		if (!Health)
		{
			continue;
		}
		const float Fraction = Health->GetHealthFraction();

		FLinearColor Fill = (Fraction <= 0.25f) ? PTKHUDColours::PlayerLow : PTKHUDColours::PlayerFill;
		if (Guard->IsDamageBoosted())
		{
			Fill = PTKHUDColours::Boosted;
		}
		DrawBar(BarX, RowY + 3.0f, BarW, 9.0f, Fraction, Fill);

		const FString Numbers = FString::Printf(TEXT("%.0f/%.0f"),
			Health->GetCurrentHealth(), Health->GetMaxHealth());
		DrawText(Numbers, PTKHUDColours::Dim, BarX + 2.0f, RowY + 12.0f, GEngine->GetSmallFont());

		if (Guard->IsDamageBoosted())
		{
			DrawText(FString::Printf(TEXT("EMPOWERED %.0fs"), Guard->GetDamageBoostRemaining()),
				PTKHUDColours::Boosted, BarX + 62.0f, RowY + 12.0f, GEngine->GetSmallFont());
		}
	}

	// The King's own row, last and separated: he is what all of the above is for.
	const float KingY = Y + Order.Num() * RowH + 6.0f;
	if (APTKKingCharacter* King = Field->GetKing())
	{
		if (UPTKHealthComponent* Health = King->GetHealthComponent())
		{
			DrawText(TEXT("KING"), PTKHUDColours::KingGold, X, KingY, GEngine->GetSmallFont());
			DrawBar(X + 92.0f, KingY + 3.0f, RosterWidth - 96.0f, 9.0f,
				Health->GetHealthFraction(),
				King->IsDead() ? PTKHUDColours::Dead : PTKHUDColours::KingFill);
			DrawText(FString::Printf(TEXT("%.0f/%.0f"),
				Health->GetCurrentHealth(), Health->GetMaxHealth()),
				PTKHUDColours::Dim, X + 94.0f, KingY + 12.0f, GEngine->GetSmallFont());
		}
	}
}

// ---------------------------------------------------------------------------
// Wave panel, top-centre.
// ---------------------------------------------------------------------------

void APTKCombatHUD::DrawWavePanel()
{
	APTKWaveManager* const Waves = GetWaveManager();
	if (!Waves || Waves->GetPhase() == EPTKWavePhase::Idle)
	{
		return;
	}

	const float CentreX = Canvas->SizeX * 0.5f;
	const float Y = 14.0f;

	DrawPanel(CentreX - 130.0f, Y - 6.0f, 260.0f, 40.0f, 0.5f);

	const FString WaveLine = FString::Printf(TEXT("WAVE %d / %d"),
		Waves->GetCurrentWave(), Waves->GetTotalWaves());
	DrawCentredText(WaveLine, CentreX, Y, PTKHUDColours::Text);

	FString Status;
	FLinearColor StatusColour = PTKHUDColours::Dim;

	switch (Waves->GetPhase())
	{
	case EPTKWavePhase::Warning:
		Status = FString::Printf(TEXT("INCOMING IN %.0f"), FMath::CeilToFloat(Waves->GetCountdown()));
		StatusColour = PTKHUDColours::Warning;
		break;
	case EPTKWavePhase::Intermission:
		Status = FString::Printf(TEXT("NEXT WAVE IN %.0f"), FMath::CeilToFloat(Waves->GetCountdown()));
		StatusColour = PTKHUDColours::KingGold;
		break;
	case EPTKWavePhase::Complete:
		Status = TEXT("ALL WAVES CLEARED");
		StatusColour = PTKHUDColours::Victory;
		break;
	case EPTKWavePhase::Stopped:
		Status = TEXT("--");
		break;
	default:
		Status = FString::Printf(TEXT("ENEMIES REMAINING: %d"), Waves->GetEnemiesRemaining());
		break;
	}
	DrawCentredText(Status, CentreX, Y + 17.0f, StatusColour);
}

// ---------------------------------------------------------------------------
// Minimap, top-right.
// ---------------------------------------------------------------------------

FVector2D APTKCombatHUD::WorldToMinimap(const FVector& World, const FVector2D& Origin,
	const FVector2D& Size) const
{
	const APTKBattlefield* Field = GetBattlefield();
	if (!Field)
	{
		return Origin;
	}
	const FVector2D N = Field->WorldToNormalised(World);
	return Origin + FVector2D(
		FMath::Clamp(N.X, 0.0f, 1.0f) * Size.X,
		FMath::Clamp(N.Y, 0.0f, 1.0f) * Size.Y);
}

void APTKCombatHUD::DrawMinimapMarker(const FVector2D& Centre, float Size,
	const FLinearColor& Colour, bool bDiamond)
{
	if (bDiamond)
	{
		// A cheap diamond: three stacked bars. Distinguishable from the square
		// blips at a glance without needing a texture or a rotated draw.
		for (int32 i = 0; i < 3; ++i)
		{
			const float W = Size * (1.0f - FMath::Abs(i - 1) * 0.45f);
			DrawRect(Colour, Centre.X - W * 0.5f, Centre.Y - Size * 0.5f + i * Size * 0.33f,
				W, Size * 0.36f);
		}
		return;
	}
	DrawRect(Colour, Centre.X - Size * 0.5f, Centre.Y - Size * 0.5f, Size, Size);
}

void APTKCombatHUD::DrawMinimap()
{
	const APTKBattlefield* Field = GetBattlefield();
	if (!Field)
	{
		return;
	}

	const float W = Canvas->SizeX * MinimapWidthFraction;
	const float H = W * (Field->GetMapHeight() / FMath::Max(Field->GetMapWidth(), 1.0f));
	const FVector2D Origin(Canvas->SizeX - W - MinimapMargin, MinimapMargin);
	const FVector2D Size(W, H);

	// Resolved once, on the first draw. bMinimapTextureResolved latches so a
	// missing asset costs one failed load rather than one per frame.
	if (!bMinimapTextureResolved)
	{
		bMinimapTextureResolved = true;
		if (!MinimapTexture)
		{
			MinimapTexture = LoadObject<UTexture2D>(nullptr,
				TEXT("/Game/PTK/Maps/T_PTK_Battlefield_Minimap"));
		}
	}

	// Background: the battlefield art itself where it is available, so the
	// minimap and the ground the player is standing on are literally the same
	// picture. No SceneCapture, no render target - one textured quad.
	if (MinimapTexture)
	{
		DrawTexture(MinimapTexture, Origin.X, Origin.Y, W, H, 0.0f, 0.0f, 1.0f, 1.0f,
			FLinearColor(1.0f, 1.0f, 1.0f, 0.92f));
	}
	else
	{
		DrawRect(FLinearColor(0.05f, 0.07f, 0.06f, 0.85f), Origin.X, Origin.Y, W, H);
	}
	DrawPanel(Origin.X, Origin.Y, W, H, 0.0f);

	// Spawn portals, and the pulse that warns a horde is on its way.
	const float Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f;
	for (const TObjectPtr<APTKSpawnPortal>& Portal : Field->GetPortals())
	{
		if (!Portal)
		{
			continue;
		}
		const FVector2D At = WorldToMinimap(Portal->GetActorLocation(), Origin, Size);
		if (Portal->IsWarning())
		{
			// Pulsing, because a static red dot in a corner is exactly the kind
			// of thing a player stops seeing after two waves.
			const float Pulse = 0.5f + 0.5f * FMath::Sin(Now * 9.0f);
			DrawMinimapMarker(At, 9.0f + Pulse * 7.0f,
				FLinearColor(1.0f, 0.25f, 0.15f, 0.45f + Pulse * 0.55f));
		}
		DrawMinimapMarker(At, 5.0f, FLinearColor(0.75f, 0.20f, 0.16f, 0.95f));
	}

	// Guard bases.
	for (const TObjectPtr<APTKGuardBase>& Base : Field->GetBases())
	{
		if (!Base)
		{
			continue;
		}
		const FVector2D At = WorldToMinimap(Base->GetActorLocation(), Origin, Size);
		if (Base->IsDestroyed())
		{
			DrawMinimapMarker(At, 7.0f, FLinearColor(0.30f, 0.30f, 0.34f, 0.9f));
			continue;
		}
		if (Base->IsUnderAttack())
		{
			const float Pulse = 0.5f + 0.5f * FMath::Sin(Now * 11.0f);
			DrawMinimapMarker(At, 12.0f + Pulse * 5.0f,
				FLinearColor(1.0f, 0.4f, 0.1f, 0.35f + Pulse * 0.5f));
		}
		DrawMinimapMarker(At, 7.0f, PTKHUDColours::BaseFill);
	}

	DrawMinimapHordes(Origin, Size);

	// Guards, then the King on top - the two things the player most needs to
	// find are drawn last so nothing can cover them.
	APTKPlayerController* const PC = Cast<APTKPlayerController>(GetOwningPlayerController());
	const APTKGuardCharacter* Played = PC ? PC->GetPlayerGuard() : nullptr;

	for (const TObjectPtr<APTKGuardCharacter>& Guard : Field->GetGuards())
	{
		if (!Guard || Guard->IsDead())
		{
			continue;
		}
		const FVector2D At = WorldToMinimap(Guard->GetActorLocation(), Origin, Size);
		if (Guard == Played)
		{
			DrawMinimapMarker(At, 13.0f, FLinearColor(PTKHUDColours::Selected.R,
				PTKHUDColours::Selected.G, PTKHUDColours::Selected.B, 0.45f));
			DrawMinimapMarker(At, 7.0f, PTKHUDColours::Selected);
		}
		else
		{
			DrawMinimapMarker(At, 6.0f, PTKHUDColours::PlayerFill);
		}
	}

	if (APTKKingCharacter* King = Field->GetKing())
	{
		const FVector2D At = WorldToMinimap(King->GetActorLocation(), Origin, Size);
		DrawMinimapMarker(At, 11.0f, PTKHUDColours::KingGold, true);
	}
}

// Enemies are CLUSTERED rather than drawn one blip each. Thirty individual dots
// on a 300-pixel map is noise; four blips labelled with their size is the
// information the player actually wants - where the pressure is and how much of
// it there is.
void APTKCombatHUD::DrawMinimapHordes(const FVector2D& Origin, const FVector2D& Size)
{
	APTKWaveManager* const Waves = GetWaveManager();
	if (!Waves)
	{
		return;
	}

	struct FCluster
	{
		FVector Sum = FVector::ZeroVector;
		int32 Count = 0;
		FVector Centre() const { return Count > 0 ? Sum / Count : FVector::ZeroVector; }
	};
	TArray<FCluster> Clusters;

	const float RadiusSq = FMath::Square(HordeClusterRadius);
	for (const TObjectPtr<APTKEnemyCharacter>& Enemy : Waves->GetLiveEnemies())
	{
		if (!Enemy || !IsValid(Enemy) || Enemy->IsDead())
		{
			continue;
		}
		const FVector At = Enemy->GetActorLocation();

		FCluster* Found = nullptr;
		for (FCluster& Cluster : Clusters)
		{
			if (FVector::DistSquared(Cluster.Centre(), At) <= RadiusSq)
			{
				Found = &Cluster;
				break;
			}
		}
		if (!Found)
		{
			Found = &Clusters.AddDefaulted_GetRef();
		}
		Found->Sum += At;
		++Found->Count;
	}

	for (const FCluster& Cluster : Clusters)
	{
		const FVector2D At = WorldToMinimap(Cluster.Centre(), Origin, Size);

		// Blip grows with the horde, but sub-linearly - otherwise a wave-5 pack
		// covers half the map and hides the base it is standing on.
		const float Marker = FMath::Clamp(5.0f + FMath::Sqrt((float)Cluster.Count) * 2.6f, 5.0f, 20.0f);
		DrawMinimapMarker(At, Marker, FLinearColor(0.92f, 0.18f, 0.14f, 0.85f));

		if (Cluster.Count > 1)
		{
			DrawText(FString::FromInt(Cluster.Count), PTKHUDColours::Text,
				At.X + Marker * 0.5f + 1.0f, At.Y - 6.0f, GEngine->GetSmallFont());
		}
	}
}

// ---------------------------------------------------------------------------
// World-space names
// ---------------------------------------------------------------------------

void APTKCombatHUD::DrawWorldLabels()
{
	const APTKBattlefield* Field = GetBattlefield();
	if (!Field)
	{
		return;
	}

	for (const TObjectPtr<APTKGuardCharacter>& Guard : Field->GetGuards())
	{
		if (!Guard || Guard->IsDead())
		{
			continue;
		}

		// Hidden at the post, shown once it leaves. A guard standing where it
		// belongs is already identified by the roster panel; the label exists to
		// answer "who is that, out there".
		const float FromHome = FVector::Dist(Guard->GetActorLocation(), Guard->GetHomePosition());
		if (FromHome <= LabelHomeThreshold)
		{
			continue;
		}

		const FVector Above = Guard->GetActorLocation() + FVector(0.0f, 0.0f, 132.0f);
		const FVector Screen = Project(Above);
		if (Screen.Z <= 0.0f || Screen.X < 0.0f || Screen.X > Canvas->SizeX
			|| Screen.Y < 0.0f || Screen.Y > Canvas->SizeY)
		{
			continue;
		}

		const FString Name = Guard->GetGuardId().ToString().ToUpper();
		DrawCentredText(Name, Screen.X, Screen.Y,
			Guard->IsDamageBoosted() ? PTKHUDColours::Boosted : PTKHUDColours::Text);
	}

	// The King's label follows the same rule, which in practice means it never
	// appears: he is anchored to his spawn and re-asserts it every tick. It is
	// written as a rule rather than as "never draw the King" so that a King who
	// is ever moved for any reason is labelled like everyone else.
	if (APTKKingCharacter* King = Field->GetKing())
	{
		const FVector Home = Field->GetNodeLocation(FName(TEXT("KING")));
		if (FVector::Dist(King->GetActorLocation(), Home) > LabelHomeThreshold && !King->IsDead())
		{
			const FVector Screen = Project(King->GetActorLocation() + FVector(0.0f, 0.0f, 150.0f));
			if (Screen.Z > 0.0f)
			{
				DrawCentredText(TEXT("KING"), Screen.X, Screen.Y, PTKHUDColours::KingGold);
			}
		}
	}
}

// ---------------------------------------------------------------------------
// Warnings
// ---------------------------------------------------------------------------

void APTKCombatHUD::RaiseWarning(const FString& Text)
{
	const float Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f;
	if (FWarningState* Existing = Warnings.Find(Text))
	{
		// Still on cooldown: refuse. This is what turns "a base is being hit"
		// from a per-frame event into an occasional banner.
		if (Now - Existing->ShownAt < WarningCooldown)
		{
			return;
		}
		Existing->ShownAt = Now;
		Existing->ExpiresAt = Now + WarningHoldTime;
		return;
	}
	Warnings.Add(Text, FWarningState{ Now, Now + WarningHoldTime });
}

void APTKCombatHUD::DrawWarnings()
{
	const APTKBattlefield* Field = GetBattlefield();
	if (!Field)
	{
		return;
	}
	const float Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f;

	for (const TObjectPtr<APTKGuardBase>& Base : Field->GetBases())
	{
		if (Base && Base->IsUnderAttack())
		{
			RaiseWarning(FString::Printf(TEXT("%s BASE UNDER ATTACK"),
				*Base->GetGuardId().ToString().ToUpper()));
		}
	}

	for (const TObjectPtr<APTKGuardCharacter>& Guard : Field->GetGuards())
	{
		if (Guard && !Guard->IsDead())
		{
			if (UPTKHealthComponent* Health = Guard->GetHealthComponent())
			{
				if (Health->GetHealthFraction() <= 0.3f)
				{
					RaiseWarning(FString::Printf(TEXT("%s IN DANGER"),
						*Guard->GetGuardId().ToString().ToUpper()));
				}
			}
		}
	}

	if (APTKKingCharacter* King = Field->GetKing())
	{
		if (King->IsAlerted() && !King->IsDead())
		{
			RaiseWarning(TEXT("KING CORE UNDER ATTACK"));
		}
	}

	if (APTKWaveManager* Waves = GetWaveManager())
	{
		// Named by the LANE the horde is actually assigned to, not just the
		// corner it comes from. Two lanes leave every corner and they end at
		// different bases, so "NorthWest" alone does not tell the player which
		// of their guards is about to be hit.
		const bool bWarning = Waves->GetPhase() == EPTKWavePhase::Warning;
		if (bWarning)
		{
			TSet<FName> Announced;
			for (const FName& RouteId : Waves->GetActiveRoutes())
			{
				const FPTKLaneRoute* Route = Field->FindRoute(RouteId);
				if (!Route || Announced.Contains(RouteId))
				{
					continue;
				}
				Announced.Add(RouteId);

				// A lane whose base has already fallen leads straight on to the
				// core, and saying so is more use than naming a ruin.
				const APTKGuardBase* Base = Field->FindBaseForGuard(Route->BaseId);
				const bool bBaseGone = !Base || Base->IsDestroyed();
				RaiseWarning(FString::Printf(TEXT("HORDE INCOMING - %s LANE, TOWARD %s"),
					*Route->PortalId.ToString().ToUpper(),
					bBaseGone ? TEXT("THE KING") : *Route->BaseId.ToString().ToUpper()));
			}
		}
	}

	// Draw whatever is still live, newest at the top, and forget the rest.
	TArray<TPair<FString, FWarningState>> Live;
	for (const TPair<FString, FWarningState>& Pair : Warnings)
	{
		if (Now < Pair.Value.ExpiresAt)
		{
			Live.Add(Pair);
		}
	}
	Live.Sort([](const TPair<FString, FWarningState>& A, const TPair<FString, FWarningState>& B)
	{
		return A.Value.ShownAt > B.Value.ShownAt;
	});

	const float CentreX = Canvas->SizeX * 0.5f;
	float Y = Canvas->SizeY * 0.16f;
	int32 Shown = 0;
	for (const TPair<FString, FWarningState>& Pair : Live)
	{
		if (Shown++ >= 3)
		{
			break;
		}
		const float Fade = FMath::Clamp((Pair.Value.ExpiresAt - Now) / FMath::Max(WarningHoldTime, 0.01f), 0.0f, 1.0f);
		FLinearColor Colour = PTKHUDColours::Warning;
		Colour.A = FMath::Clamp(Fade * 1.6f, 0.0f, 1.0f);
		DrawCentredText(Pair.Key, CentreX, Y, Colour);
		Y += 20.0f;
	}
}

// ---------------------------------------------------------------------------
// Result banner
// ---------------------------------------------------------------------------

void APTKCombatHUD::DrawResultBanner()
{
	const APTKGameModeBase* Mode = GetWorld() ? GetWorld()->GetAuthGameMode<APTKGameModeBase>() : nullptr;
	if (!Mode || !Mode->IsMatchOver())
	{
		return;
	}

	const bool bWon = Mode->GetMatchResult() == EPTKMatchResult::Victory;
	const float CentreX = Canvas->SizeX * 0.5f;
	const float CentreY = Canvas->SizeY * 0.42f;

	DrawRect(FLinearColor(0.0f, 0.0f, 0.0f, 0.55f), 0.0f, CentreY - 34.0f, Canvas->SizeX, 92.0f);

	DrawCentredText(bWon ? TEXT("VICTORY") : TEXT("KING DEFEATED"),
		CentreX, CentreY, bWon ? PTKHUDColours::Victory : PTKHUDColours::PlayerLow, 2.4f);
	DrawCentredText(bWon ? TEXT("THE KING SURVIVED") : TEXT("GAME OVER"),
		CentreX, CentreY + 40.0f, PTKHUDColours::Text, 1.4f);
}

// ---------------------------------------------------------------------------
// Guard switching - console entry points
// ---------------------------------------------------------------------------
namespace PTKSwitchKeys
{
	/** Slot 1..5 -> the number key a player would press. */
	static FKey ForSlot(int32 Slot)
	{
		switch (Slot)
		{
		case 1: return EKeys::One;
		case 2: return EKeys::Two;
		case 3: return EKeys::Three;
		case 4: return EKeys::Four;
		case 5: return EKeys::Five;
		default: return EKeys::Invalid;
		}
	}
}

void APTKCombatHUD::PTKSwitchKey(int32 Slot, float Delay)
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	const FKey Key = PTKSwitchKeys::ForSlot(Slot);
	if (!Key.IsValid())
	{
		UE_LOG(LogPTK, Error, TEXT("PTKSwitchKey: %d is not a guard slot"), Slot);
		return;
	}

	FTimerHandle Handle;
	World->GetTimerManager().SetTimer(Handle,
		FTimerDelegate::CreateWeakLambda(this, [this, Key, Slot]()
		{
			APlayerController* const PC = GetOwningPlayerController();
			UWorld* const W = GetWorld();
			if (!PC || !W)
			{
				return;
			}

			UE_LOG(LogPTK, Warning, TEXT("PTKSwitchKey: pressing '%s' for slot %d"),
				*Key.ToString(), Slot);

			// Straight into the player's own input pipeline, so the mapping
			// context and the action asset are both on trial here, not just the
			// C++ behind them.
			// Device 0 is the default keyboard/mouse. Built by hand rather than
			// asked of IPlatformInputDeviceMapper, which lives in ApplicationCore
			// - a whole module dependency for one constant.
			const FInputDeviceId Device = FInputDeviceId::CreateFromInternalId(0);
			PC->InputKey(FInputKeyEventArgs(nullptr, Device, Key, IE_Pressed,
				FPlatformTime::Cycles64()));

			// Released shortly after, or the key stays down for the rest of the
			// session and the next press of a DIFFERENT number arrives with this
			// one still held.
			FTimerHandle Release;
			W->GetTimerManager().SetTimer(Release,
				FTimerDelegate::CreateWeakLambda(this, [this, Key, Device]()
				{
					if (APlayerController* const P = GetOwningPlayerController())
					{
						P->InputKey(FInputKeyEventArgs(nullptr, Device, Key, IE_Released,
							FPlatformTime::Cycles64()));
					}
				}), 0.1f, false);
		}), FMath::Max(Delay, 0.01f), false);
}

void APTKCombatHUD::PTKSwitchGuard(int32 Slot, float Delay)
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	FTimerHandle Handle;
	World->GetTimerManager().SetTimer(Handle,
		FTimerDelegate::CreateWeakLambda(this, [this, Slot]()
		{
			if (APTKPlayerController* const PC =
					Cast<APTKPlayerController>(GetOwningPlayerController()))
			{
				PC->SelectGuardSlot(Slot);
			}
			else
			{
				UE_LOG(LogPTK, Error,
					TEXT("PTKSwitchGuard: the player controller is not an APTKPlayerController"));
			}
		}), FMath::Max(Delay, 0.01f), false);
}

void APTKCombatHUD::PTKGuards(float Delay)
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	FTimerHandle Handle;
	World->GetTimerManager().SetTimer(Handle,
		FTimerDelegate::CreateWeakLambda(this, [this]()
		{
			if (const APTKPlayerController* const PC =
					Cast<APTKPlayerController>(GetOwningPlayerController()))
			{
				PC->LogRoster(TEXT("PTKGuards"));
			}
		}), FMath::Max(Delay, 0.01f), false);
}

void APTKCombatHUD::PTKKillSlot(int32 Slot, float Delay)
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	FTimerHandle Handle;
	World->GetTimerManager().SetTimer(Handle,
		FTimerDelegate::CreateWeakLambda(this, [this, Slot]()
		{
			const APTKPlayerController* const PC =
				Cast<APTKPlayerController>(GetOwningPlayerController());
			APTKGuardCharacter* const Guard = PC ? PC->GetGuardInSlot(Slot) : nullptr;
			if (!Guard)
			{
				UE_LOG(LogPTK, Error, TEXT("PTKKillSlot: no guard in slot %d"), Slot);
				return;
			}
			if (UPTKHealthComponent* const Health = Guard->GetHealthComponent())
			{
				UE_LOG(LogPTK, Warning,
					TEXT("*** DEBUG KILL (console command, NOT gameplay) *** ")
					TEXT("felling slot %d %s from %.0f HP"),
					Slot, *Guard->GetGuardId().ToString(), Health->GetCurrentHealth());
				// Immunity would otherwise swallow this while Aegis is braced,
				// and a test that silently fails to kill is worse than no test.
				Health->SetDamageImmune(false);
				Health->ApplyDamage(Health->GetCurrentHealth(), Guard);
			}
		}), FMath::Max(Delay, 0.01f), false);
}

void APTKCombatHUD::PTKPressKey(const FString& KeyName, float Hold, float Delay)
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	const FKey Key(*KeyName);
	if (!Key.IsValid())
	{
		UE_LOG(LogPTK, Error, TEXT("PTKPressKey: '%s' is not a key"), *KeyName);
		return;
	}

	const float HoldFor = FMath::Clamp(Hold, 0.05f, 30.0f);

	FTimerHandle Handle;
	World->GetTimerManager().SetTimer(Handle,
		FTimerDelegate::CreateWeakLambda(this, [this, Key, HoldFor]()
		{
			APlayerController* const PC = GetOwningPlayerController();
			UWorld* const W = GetWorld();
			if (!PC || !W)
			{
				return;
			}
			const FInputDeviceId Device = FInputDeviceId::CreateFromInternalId(0);
			UE_LOG(LogPTK, Warning, TEXT("PTKPressKey: holding '%s' for %.1fs on %s"),
				*Key.ToString(), HoldFor, *GetNameSafe(PC->GetPawn()));
			PC->InputKey(FInputKeyEventArgs(nullptr, Device, Key, IE_Pressed,
				FPlatformTime::Cycles64()));

			FTimerHandle Release;
			W->GetTimerManager().SetTimer(Release,
				FTimerDelegate::CreateWeakLambda(this, [this, Key, Device]()
				{
					if (APlayerController* const P = GetOwningPlayerController())
					{
						P->InputKey(FInputKeyEventArgs(nullptr, Device, Key, IE_Released,
							FPlatformTime::Cycles64()));
						UE_LOG(LogPTK, Warning, TEXT("PTKPressKey: released '%s'"),
							*Key.ToString());
					}
				}), HoldFor, false);
		}), FMath::Max(Delay, 0.01f), false);
}

// ---------------------------------------------------------------------------
// Aim rigs - stationary dummies on known bearings
// ---------------------------------------------------------------------------
namespace PTKAimRig
{
	static const TCHAR* const SwarmClass =
		TEXT("/Game/PTK/Characters/Enemies/SwarmNode/Blueprints/BP_SwarmNode.BP_SwarmNode_C");
	static const TCHAR* const LabelPrefix = TEXT("AimDummy_");
}

APTKTopDownCharacter* APTKCombatHUD::ClearFieldForRig()
{
	UWorld* const World = GetWorld();
	APTKTopDownCharacter* const Guard =
		Cast<APTKTopDownCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
	if (!World || !Guard)
	{
		UE_LOG(LogPTK, Error, TEXT("AIM RIG | no played guard"));
		return nullptr;
	}

	// Everything else goes. A shot that is stopped by a swarm node wandering
	// across the line proves nothing about aim, and leaving the field populated
	// is the difference between a measurement and an anecdote.
	int32 Removed = 0;
	for (TActorIterator<APTKEnemyCharacter> It(World); It; ++It)
	{
		if (IsValid(*It))
		{
			It->Destroy();
			++Removed;
		}
	}
	// The other four stop thinking too. A Sentinel at his post will happily
	// splash a dummy that was put there to measure Wraith, and the log would
	// then credit the hit to the wrong bow.
	int32 Silenced = 0;
	for (TActorIterator<APTKGuardCharacter> It(World); It; ++It)
	{
		if (!IsValid(*It) || *It == Guard)
		{
			continue;
		}
		if (APTKGuardAIController* const AI = Cast<APTKGuardAIController>(It->GetController()))
		{
			AI->SetAIEnabled(false);
			++Silenced;
		}
	}
	UE_LOG(LogPTK, Warning,
		TEXT("AIM RIG | field cleared (%d enemies removed, %d guard AI silenced)"),
		Removed, Silenced);
	return Guard;
}

AActor* APTKCombatHUD::SpawnDummy(const FVector& Where, const FString& Label)
{
	UWorld* const World = GetWorld();
	UClass* const Class = LoadClass<APTKEnemyCharacter>(nullptr, PTKAimRig::SwarmClass);
	if (!World || !Class)
	{
		UE_LOG(LogPTK, Error, TEXT("AIM RIG | BP_SwarmNode could not be loaded"));
		return nullptr;
	}

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	APTKEnemyCharacter* const Dummy =
		World->SpawnActor<APTKEnemyCharacter>(Class, Where, FRotator::ZeroRotator, Params);
	if (!Dummy)
	{
		return nullptr;
	}

	// Stationary on purpose: its own Tick is what chases and attacks, so
	// switching that off leaves a body that can still be hit and still bleeds,
	// but cannot walk out of the line being measured.
	Dummy->SetActorTickEnabled(false);
	Dummy->SetActorLabel(PTKAimRig::LabelPrefix + Label);
	UE_LOG(LogPTK, Warning, TEXT("AIM RIG | dummy %-6s at %s"),
		*Label, *Where.ToCompactString());
	return Dummy;
}

void APTKCombatHUD::LogDummies(const FString& Stage)
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}
	UE_LOG(LogPTK, Warning, TEXT("AIM RIG | %s"), *Stage);
	for (TActorIterator<APTKEnemyCharacter> It(World); It; ++It)
	{
		APTKEnemyCharacter* const Dummy = *It;
		if (!IsValid(Dummy) || !Dummy->GetActorLabel().StartsWith(PTKAimRig::LabelPrefix))
		{
			continue;
		}
		const UPTKHealthComponent* const Health = Dummy->GetHealthComponent();
		const float Now = Health ? Health->GetCurrentHealth() : -1.0f;
		const float Max = Health ? Health->GetMaxHealth() : -1.0f;
		UE_LOG(LogPTK, Warning, TEXT("AIM RIG | %-18s HP %6.1f/%6.1f  %s"),
			*Dummy->GetActorLabel(), Now, Max,
			(Now < Max) ? TEXT("HIT") : TEXT("untouched"));
	}
}

void APTKCombatHUD::PTKAimTest(float Distance, float StartDelay)
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	FTimerHandle Setup;
	World->GetTimerManager().SetTimer(Setup,
		FTimerDelegate::CreateWeakLambda(this, [this, Distance]()
		{
			APTKTopDownCharacter* const Guard = ClearFieldForRig();
			UWorld* const W = GetWorld();
			if (!Guard || !W)
			{
				return;
			}

			// Bearings come from the guard's OWN screen basis, so "Up" here is
			// the same Up the flipbook and the shot use. Building them from
			// world axes would be testing my arithmetic, not the game's.
			const FVector Here = Guard->GetActorLocation();
			const FVector R = Guard->GetMovementRightVector();
			const FVector U = Guard->GetMovementUpVector();
			SpawnDummy(Here + U * Distance,  TEXT("Up"));
			SpawnDummy(Here - U * Distance,  TEXT("Down"));
			SpawnDummy(Here - R * Distance,  TEXT("Left"));
			SpawnDummy(Here + R * Distance,  TEXT("Right"));

			const EPTKFacingDirection Order[] = {
				EPTKFacingDirection::Up, EPTKFacingDirection::Down,
				EPTKFacingDirection::Left, EPTKFacingDirection::Right };

			for (int32 i = 0; i < 4; ++i)
			{
				const EPTKFacingDirection Dir = Order[i];
				FTimerHandle Shot;
				W->GetTimerManager().SetTimer(Shot,
					FTimerDelegate::CreateWeakLambda(this, [this, Dir]()
					{
						APTKTopDownCharacter* const G =
							Cast<APTKTopDownCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
						if (!G) { return; }
						G->SetMoveInput(FVector2D::ZeroVector);
						G->SetFacingDirection(Dir);
						UE_LOG(LogPTK, Warning, TEXT("AIM RIG | firing %s"),
							*UPTKTypesLibrary::DirectionToString(Dir));
						G->StartAttack();
					}), 0.6f + i * 1.4f, false);
			}

			FTimerHandle Done;
			W->GetTimerManager().SetTimer(Done,
				FTimerDelegate::CreateWeakLambda(this, [this]()
				{
					LogDummies(TEXT("aim results"));
				}), 0.6f + 4 * 1.4f + 1.0f, false);
		}), FMath::Max(StartDelay, 0.01f), false);
}

void APTKCombatHUD::PTKSplashTest(float Distance, float StartDelay)
{
	UWorld* const World = GetWorld();
	if (!World)
	{
		return;
	}

	FTimerHandle Setup;
	World->GetTimerManager().SetTimer(Setup,
		FTimerDelegate::CreateWeakLambda(this, [this, Distance]()
		{
			APTKTopDownCharacter* const Guard = ClearFieldForRig();
			UWorld* const W = GetWorld();
			if (!Guard || !W)
			{
				return;
			}

			const FVector Here = Guard->GetActorLocation();
			const FVector R = Guard->GetMovementRightVector();
			const FVector U = Guard->GetMovementUpVector();

			// Three inside one 96 uu blast, one well outside it. The far dummy
			// is the control: a splash that catches it is not a 96 uu splash.
			SpawnDummy(Here + U * Distance,                    TEXT("Centre"));
			SpawnDummy(Here + U * Distance + R * 55.0f,        TEXT("Near_R"));
			SpawnDummy(Here + U * (Distance + 60.0f),          TEXT("Near_U"));
			SpawnDummy(Here + U * Distance + R * 220.0f,       TEXT("Far"));

			FTimerHandle Shot;
			W->GetTimerManager().SetTimer(Shot,
				FTimerDelegate::CreateWeakLambda(this, [this]()
				{
					APTKTopDownCharacter* const G =
						Cast<APTKTopDownCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));
					if (!G) { return; }
					G->SetMoveInput(FVector2D::ZeroVector);
					G->SetFacingDirection(EPTKFacingDirection::Up);
					UE_LOG(LogPTK, Warning, TEXT("AIM RIG | one shot into the cluster"));
					G->StartAttack();
				}), 0.8f, false);

			FTimerHandle Done;
			W->GetTimerManager().SetTimer(Done,
				FTimerDelegate::CreateWeakLambda(this, [this]()
				{
					LogDummies(TEXT("splash results"));
				}), 2.6f, false);
		}), FMath::Max(StartDelay, 0.01f), false);
}

// ---------------------------------------------------------------------------
// Wave, base and targeting console commands. MANUAL ONLY - nothing calls these.
// ---------------------------------------------------------------------------

void APTKCombatHUD::PTKWave(int32 Wave)
{
	if (APTKWaveManager* Waves = GetWaveManager())
	{
		Waves->DebugSkipToWave(Wave);
	}
	else
	{
		UE_LOG(LogPTK, Warning, TEXT("no wave manager in this level"));
	}
}

void APTKCombatHUD::PTKWaveStatus()
{
	APTKWaveManager* const Waves = GetWaveManager();
	if (!Waves)
	{
		UE_LOG(LogPTK, Warning, TEXT("no wave manager in this level"));
		return;
	}

	const UEnum* PhaseEnum = StaticEnum<EPTKWavePhase>();
	UE_LOG(LogPTK, Log, TEXT("WAVE STATUS | wave %d/%d | phase %s | countdown %.1f | remaining %d"),
		Waves->GetCurrentWave(), Waves->GetTotalWaves(),
		PhaseEnum ? *PhaseEnum->GetNameStringByValue((int64)Waves->GetPhase()) : TEXT("?"),
		Waves->GetCountdown(), Waves->GetEnemiesRemaining());

	for (APTKSpawnPortal* Portal : Waves->GetActivePortals())
	{
		if (Portal)
		{
			UE_LOG(LogPTK, Log, TEXT("  active portal %s | warning %.1fs"),
				*Portal->GetPortalId().ToString(), Portal->GetWarningRemaining());
		}
	}
}

void APTKCombatHUD::PTKBaseDamage(const FString& BaseName, float Amount)
{
	const APTKBattlefield* Field = GetBattlefield();
	if (!Field)
	{
		return;
	}
	for (const TObjectPtr<APTKGuardBase>& Base : Field->GetBases())
	{
		if (Base && Base->GetGuardId().ToString().Equals(BaseName, ESearchCase::IgnoreCase))
		{
			Base->DebugApplyDamage(Amount);
			return;
		}
	}
	UE_LOG(LogPTK, Warning, TEXT("no base called %s"), *BaseName);
}

void APTKCombatHUD::PTKBaseKill(const FString& BaseName)
{
	PTKBaseDamage(BaseName, 999999.0f);
}

void APTKCombatHUD::PTKBases()
{
	const APTKBattlefield* Field = GetBattlefield();
	if (!Field)
	{
		UE_LOG(LogPTK, Warning, TEXT("no battlefield in this level"));
		return;
	}
	UE_LOG(LogPTK, Log, TEXT("--- GUARD BASES ---"));
	for (const TObjectPtr<APTKGuardBase>& Base : Field->GetBases())
	{
		if (!Base)
		{
			continue;
		}
		UPTKHealthComponent* const Health = Base->GetHealthComponent();
		UE_LOG(LogPTK, Log, TEXT("  %-10s %7.0f / %-7.0f %s"),
			*Base->GetGuardId().ToString(),
			Health ? Health->GetCurrentHealth() : 0.0f,
			Health ? Health->GetMaxHealth() : 0.0f,
			Base->IsDestroyed() ? TEXT("DESTROYED") : TEXT("standing"));
	}
}

void APTKCombatHUD::PTKKingPower()
{
	if (APTKKingCharacter* King = FindKing())
	{
		UE_LOG(LogPTK, Log, TEXT("PTKKingPower -> %s"),
			King->TriggerEmergencyPower() ? TEXT("granted") : TEXT("refused (already spent, or no living guard)"));
	}
}

void APTKCombatHUD::PTKTargets(int32 MaxLines)
{
	UE_LOG(LogPTK, Log, TEXT("--- ENEMY TARGETS ---"));
	int32 Shown = 0;
	for (TActorIterator<APTKEnemyCharacter> It(GetWorld()); It; ++It)
	{
		APTKEnemyCharacter* const Enemy = *It;
		if (!IsValid(Enemy) || Enemy->IsDead() || Shown >= MaxLines)
		{
			continue;
		}
		++Shown;
		UE_LOG(LogPTK, Log, TEXT("  %-22s -> %-24s  %.0f uu"),
			*Enemy->GetName(), *GetNameSafe(Enemy->GetTarget()), Enemy->GetDistanceToTarget());
	}
	if (Shown == 0)
	{
		UE_LOG(LogPTK, Log, TEXT("  (no living enemies)"));
	}
}

void APTKCombatHUD::PTKBaseProbe(const FString& BaseName)
{
	const APTKBattlefield* Field = GetBattlefield();
	UWorld* const World = GetWorld();
	if (!Field || !World)
	{
		return;
	}

	APTKGuardBase* Base = nullptr;
	for (const TObjectPtr<APTKGuardBase>& Candidate : Field->GetBases())
	{
		if (Candidate && Candidate->GetGuardId().ToString().Equals(BaseName, ESearchCase::IgnoreCase))
		{
			Base = Candidate;
			break;
		}
	}
	if (!Base)
	{
		UE_LOG(LogPTK, Warning, TEXT("PROBE | no base called %s"), *BaseName);
		return;
	}

	const FVector At = Base->GetActorLocation();
	UE_LOG(LogPTK, Log, TEXT("PROBE | base %s at %s | destroyed=%d | HP %.0f"),
		*BaseName, *At.ToString(), Base->IsDestroyed() ? 1 : 0,
		Base->GetHealthComponent() ? Base->GetHealthComponent()->GetCurrentHealth() : -1.0f);

	// Does an object-type overlap actually return the base's capsule?
	TArray<FOverlapResult> Overlaps;
	FCollisionObjectQueryParams ObjectTypes;
	ObjectTypes.AddObjectTypesToQuery(ECC_Pawn);
	ObjectTypes.AddObjectTypesToQuery(ECC_WorldDynamic);
	FCollisionQueryParams Params(SCENE_QUERY_STAT(PTKBaseProbe), false);

	World->OverlapMultiByObjectType(Overlaps, At, FQuat::Identity, ObjectTypes,
		FCollisionShape::MakeSphere(60.0f), Params);

	bool bFoundBase = false;
	for (const FOverlapResult& Result : Overlaps)
	{
		AActor* const Found = Result.GetActor();
		if (Found == Base)
		{
			bFoundBase = true;
		}
		UE_LOG(LogPTK, Log, TEXT("PROBE |   overlap returned %s"), *GetNameSafe(Found));
	}
	UE_LOG(LogPTK, Warning, TEXT("PROBE | overlap %s the base capsule"),
		bFoundBase ? TEXT("FOUND") : TEXT("DID NOT FIND"));

	// What is the nearest enemy doing about it?
	APTKEnemyCharacter* Nearest = nullptr;
	float NearestDist = TNumericLimits<float>::Max();
	for (TActorIterator<APTKEnemyCharacter> It(World); It; ++It)
	{
		APTKEnemyCharacter* const Enemy = *It;
		if (!IsValid(Enemy) || Enemy->IsDead())
		{
			continue;
		}
		const float Dist = FVector::Dist(At, Enemy->GetActorLocation());
		if (Dist < NearestDist)
		{
			NearestDist = Dist;
			Nearest = Enemy;
		}
	}

	if (!Nearest)
	{
		UE_LOG(LogPTK, Log, TEXT("PROBE | no living enemy anywhere"));
		return;
	}

	UE_LOG(LogPTK, Warning,
		TEXT("PROBE | nearest enemy %s at %.0f uu | reach %.0f | hit radius %.0f | state %s | target %s | valid victim=%d"),
		*Nearest->GetName(), NearestDist, Nearest->GetAttackReach(),
		Nearest->GetAttackHitRadius(),
		*UPTKTypesLibrary::EnemyStateToString(Nearest->GetEnemyState()),
		*GetNameSafe(Nearest->GetTarget()),
		Nearest->IsValidAttackVictim(Base) ? 1 : 0);
}
