// Protect the King - 2D. Prototype combat HUD.

#include "Core/PTKCombatHUD.h"

#include "Characters/PTKEnemyCharacter.h"
#include "Characters/PTKTopDownCharacter.h"
#include "Components/PTKHealthComponent.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"

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

	if (Player && Player->IsDead())
	{
		DrawDefeatBanner();
	}
}
