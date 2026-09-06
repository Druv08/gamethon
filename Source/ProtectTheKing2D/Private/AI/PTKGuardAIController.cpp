// Protect the King - 2D. The one guard AI.

#include "AI/PTKGuardAIController.h"

#include "Characters/PTKGuardCharacter.h"
#include "Combat/PTKCombatTarget.h"
#include "DrawDebugHelpers.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "ProtectTheKing2D.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKGuardAIController)

APTKGuardAIController::APTKGuardAIController()
{
	PrimaryActorTick.bCanEverTick = true;
	// A 2D guard has no line of sight to lose and no perception config to get
	// wrong; distance is the whole of its awareness.
	bAttachToPawn = false;
}

void APTKGuardAIController::OnPossess(APawn* InPawn)
{
	Super::OnPossess(InPawn);

	APTKGuardCharacter* const Guard = Cast<APTKGuardCharacter>(InPawn);
	if (!Guard)
	{
		// Deliberately loud. This controller only knows how to drive a guard,
		// and silently possessing something else would look like broken AI.
		UE_LOG(LogPTK, Warning,
			TEXT("GUARD AI | %s possessed %s, which is not an APTKGuardCharacter"),
			*GetName(), *GetNameSafe(InPawn));
		return;
	}

	Target = nullptr;
	TargetRefreshTimer = 0.0f;
	DefendCooldownRemaining = 0.0f;
	AIState = EPTKGuardAIState::Hold;

	UE_LOG(LogPTK, Log,
		TEXT("GUARD AI | %s takes over %s | home (%.0f, %.0f) | detect %.0f | chase %.0f | reach %.0f"),
		*GetName(), *Guard->GetName(),
		Guard->GetHomePosition().X, Guard->GetHomePosition().Z,
		Guard->GetDetectionRange(), Guard->GetMaxChaseDistance(),
		Guard->GetAttackReach());
}

void APTKGuardAIController::OnUnPossess()
{
	// The player is taking this guard, or it is being destroyed. Either way the
	// AI must stop deciding things about a pawn it no longer holds.
	if (APTKGuardCharacter* const Guard = Cast<APTKGuardCharacter>(GetPawn()))
	{
		Guard->SetMoveInput(FVector2D::ZeroVector);
		UE_LOG(LogPTK, Log, TEXT("GUARD AI | %s releases %s"), *GetName(), *Guard->GetName());
	}
	Target = nullptr;
	AIState = EPTKGuardAIState::Inactive;
	Super::OnUnPossess();
}

void APTKGuardAIController::SetAIEnabled(bool bEnabled)
{
	if (bAIEnabled == bEnabled)
	{
		return;
	}
	bAIEnabled = bEnabled;
	if (!bEnabled)
	{
		if (APTKGuardCharacter* const Guard = Cast<APTKGuardCharacter>(GetPawn()))
		{
			Guard->SetMoveInput(FVector2D::ZeroVector);
		}
		Target = nullptr;
		AIState = EPTKGuardAIState::Inactive;
	}
	else
	{
		AIState = EPTKGuardAIState::Hold;
	}
}

void APTKGuardAIController::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	APTKGuardCharacter* const Guard = Cast<APTKGuardCharacter>(GetPawn());
	if (!Guard)
	{
		AIState = EPTKGuardAIState::Inactive;
		return;
	}

	if (Guard->IsDead())
	{
		// A corpse decides nothing. The death itself is handled entirely by
		// the character - this only stops the AI talking to it.
		if (AIState != EPTKGuardAIState::Dead)
		{
			UE_LOG(LogPTK, Log, TEXT("GUARD AI | %s is dead - AI stopped"), *Guard->GetName());
			AIState = EPTKGuardAIState::Dead;
			Target = nullptr;
		}
		return;
	}

	if (!bAIEnabled)
	{
		return;
	}

	DefendCooldownRemaining = FMath::Max(0.0f, DefendCooldownRemaining - DeltaSeconds);
	TargetRefreshTimer -= DeltaSeconds;

	// Re-acquire when the current target is gone, has been dragged out of the
	// defended area, or the refresh interval has elapsed.
	if (!IsTargetStillValid(Guard, Target) || TargetRefreshTimer <= 0.0f)
	{
		TargetRefreshTimer = TargetRefreshInterval;
		AActor* const Found = FindTarget(Guard);
		if (Found != Target)
		{
			UE_LOG(LogPTK, Verbose, TEXT("GUARD AI | %s target: %s -> %s"),
				*Guard->GetName(), *GetNameSafe(Target), *GetNameSafe(Found));
			Target = Found;
		}
	}

	const FVector Here = Guard->GetActorLocation();

	if (bDrawAIRanges)
	{
		const FVector Home = Guard->GetHomePosition();
		DrawDebugCircle(GetWorld(), Home, Guard->GetMaxChaseDistance(), 32,
			FColor::Yellow, false, -1.0f, 0, 1.0f, FVector(1, 0, 0), FVector(0, 0, 1), false);
		DrawDebugCircle(GetWorld(), Here, Guard->GetAttackReach(), 24,
			FColor::Green, false, -1.0f, 0, 1.0f, FVector(1, 0, 0), FVector(0, 0, 1), false);
	}

	if (Target)
	{
		const FVector To = Target->GetActorLocation() - Here;
		const float Distance = To.Size();
		// Reach is the guard's OWN number, so this single line is what makes a
		// melee guard close and a ranged one hold its ground.
		const float EngageAt = Guard->GetAttackReach() * Guard->GetAIEngageFraction();

		ConsiderDefending(Guard, DeltaSeconds);

		if (Distance <= EngageAt)
		{
			AIState = EPTKGuardAIState::Attack;
			// Stop, face the target, swing. Facing has to be set explicitly:
			// the character only turns from movement input, and this guard is
			// deliberately standing still.
			Guard->SetMoveInput(FVector2D::ZeroVector);
			FaceLocation(Guard, Target->GetActorLocation());
			Guard->StartAttack();
		}
		else
		{
			AIState = EPTKGuardAIState::Engage;
			Guard->SetMoveInput(ToScreenInput(Guard, To));
		}
	}
	else
	{
		// Nothing to fight: go back to the post and stand there.
		const FVector ToHome = Guard->GetHomePosition() - Here;
		if (ToHome.Size() <= Guard->GetAIHomeTolerance())
		{
			AIState = EPTKGuardAIState::Hold;
			Guard->SetMoveInput(FVector2D::ZeroVector);
		}
		else
		{
			AIState = EPTKGuardAIState::Return;
			Guard->SetMoveInput(ToScreenInput(Guard, ToHome));
		}
	}

	if (AIState != LoggedState)
	{
		LoggedState = AIState;
		UE_LOG(LogPTK, Log, TEXT("GUARD AI | %s -> %s | target %s"),
			*Guard->GetName(), *UPTKTypesLibrary::GuardAIStateToString(AIState),
			*GetNameSafe(Target));
	}
}

// ---------------------------------------------------------------------------
bool APTKGuardAIController::IsTargetStillValid(const APTKGuardCharacter* Guard,
	const AActor* Candidate) const
{
	if (!Guard || !PTKCombat::IsHostileTarget(Guard, Candidate))
	{
		return false;
	}
	// Bounded by distance from the POST, not from the guard. That is what stops
	// an enemy walking a guard off its ground one step at a time.
	return FVector::Dist(Guard->GetHomePosition(), Candidate->GetActorLocation())
		<= Guard->GetMaxChaseDistance();
}

AActor* APTKGuardAIController::FindTarget(const APTKGuardCharacter* Guard) const
{
	if (!Guard || !GetWorld())
	{
		return nullptr;
	}

	const FVector Here = Guard->GetActorLocation();
	const FVector Home = Guard->GetHomePosition();
	const float Detection = Guard->GetDetectionRange();
	const float Leash = Guard->GetMaxChaseDistance();

	AActor* Best = nullptr;
	float BestDistanceSq = TNumericLimits<float>::Max();

	// Hostility comes from the shared rule, so a guard can never pick another
	// guard or the King: they are different teams but the same side.
	for (TActorIterator<APTKTopDownCharacter> It(GetWorld()); It; ++It)
	{
		AActor* const Candidate = *It;
		if (!PTKCombat::IsHostileTarget(Guard, Candidate))
		{
			continue;
		}
		const FVector Where = Candidate->GetActorLocation();
		if (FVector::Dist(Home, Where) > Leash)
		{
			continue;
		}
		const float DistanceSq = FVector::DistSquared(Here, Where);
		if (DistanceSq > Detection * Detection)
		{
			continue;
		}
		if (DistanceSq < BestDistanceSq)
		{
			BestDistanceSq = DistanceSq;
			Best = Candidate;
		}
	}
	return Best;
}

int32 APTKGuardAIController::CountHostilesWithin(const APTKGuardCharacter* Guard,
	float Radius) const
{
	if (!Guard || !GetWorld())
	{
		return 0;
	}
	const FVector Here = Guard->GetActorLocation();
	int32 Count = 0;
	for (TActorIterator<APTKTopDownCharacter> It(GetWorld()); It; ++It)
	{
		if (PTKCombat::IsHostileTarget(Guard, *It)
			&& FVector::Dist(Here, It->GetActorLocation()) <= Radius)
		{
			++Count;
		}
	}
	return Count;
}

FVector2D APTKGuardAIController::ToScreenInput(const APTKGuardCharacter* Guard,
	const FVector& WorldOffset) const
{
	if (!Guard)
	{
		return FVector2D::ZeroVector;
	}
	// Projected onto the camera's basis rather than onto world axes - screen
	// right is not +X in this project, and the AI must not be the one place
	// that forgets it.
	const FVector2D Screen(
		FVector::DotProduct(WorldOffset, Guard->GetMovementRightVector()),
		FVector::DotProduct(WorldOffset, Guard->GetMovementUpVector()));
	return Screen.GetSafeNormal();
}

void APTKGuardAIController::FaceLocation(APTKGuardCharacter* Guard, const FVector& Where) const
{
	if (!Guard)
	{
		return;
	}
	const FVector2D Bearing = ToScreenInput(Guard, Where - Guard->GetActorLocation());
	if (Bearing.IsNearlyZero())
	{
		return;
	}
	Guard->SetFacingDirection(UPTKTypesLibrary::DirectionFromInput(
		Bearing, Guard->GetFacingDirection(), 0.0f, 0.0f));
}

void APTKGuardAIController::ConsiderDefending(APTKGuardCharacter* Guard, float /*DeltaSeconds*/)
{
	if (DefendCooldownRemaining > 0.0f || Guard->IsDefending() || Guard->IsAttacking())
	{
		return;
	}
	if (CountHostilesWithin(Guard, Guard->GetAttackReach()) < Guard->GetAIDefendMinEnemies())
	{
		return;
	}
	// No check for "is this Aegis" anywhere: StartDefend refuses without
	// defence art, so every other guard silently declines.
	if (Guard->StartDefend())
	{
		DefendCooldownRemaining = Guard->GetAIDefendCooldown();
		UE_LOG(LogPTK, Log, TEXT("GUARD AI | %s raises its shield (next in %.0fs)"),
			*Guard->GetName(), DefendCooldownRemaining);
	}
}
